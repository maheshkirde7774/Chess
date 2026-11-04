import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.db import init_db
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def _create_four_player_match(client, is_private=False):
    host = client.post("/rooms", json={
        "player_name": "Host", "is_private": is_private,
    }).json()
    for seat in range(3):
        response = client.post("/rooms/join", json={
            "room_code": host["room_code"], "player_name": f"Player {seat + 2}",
        })
        assert response.status_code == 200
    response = client.post(
        f"/rooms/{host['room_code']}/start",
        json={"player_id": host["player_id"]},
    )
    assert response.status_code == 200
    return host


def test_four_player_spectator_sync_updates_read_only_and_counts(client):
    host = _create_four_player_match(client)
    code = host["room_code"]
    assert code in [
        game["room_code"] for game in client.get("/spectator/live-games").json()
    ]

    with client.websocket_connect(f"/ws/spectate/{code}") as spectator:
        spectator.send_json({"type": "SPECTATE"})
        initial = spectator.receive_json()
        assert initial["type"] == "SYNC_STATE"
        assert initial["game_mode"] == "four_player"
        assert initial["game_state"]["current_turn"] == 1
        assert "player_id" not in str(initial)
        assert "profile_id" not in str(initial)
        assert spectator.receive_json()["spectator_count"] == 1
        spectator.send_json({"type": "PING"})
        assert spectator.receive_json()["type"] == "PONG"

        spectator.send_json({"type": "MOVE", "from": [12, 6], "to": [10, 6]})
        denied = spectator.receive_json()
        assert denied["type"] == "ERROR"
        assert "read-only" in denied["message"]
        assert client.get(f"/rooms/{code}").json()["current_turn"] == 1

        moved = client.post(f"/rooms/{code}/move", json={
            "player_id": host["player_id"],
            "from_sq": [12, 6],
            "to_sq": [10, 6],
        })
        assert moved.status_code == 200
        update = spectator.receive_json()
        assert update["type"] == "MOVE_MADE"
        assert update["game_state"]["current_turn"] == 2
        assert update["move"]["from"] == [12, 6]
    assert client.get("/spectator/live-games").status_code == 200
    with client.websocket_connect(f"/ws/spectate/{code}") as reconnect:
        reconnect.send_json({"type": "SPECTATE"})
        assert reconnect.receive_json()["type"] == "SYNC_STATE"
        assert reconnect.receive_json()["spectator_count"] == 1


def test_private_four_player_match_requires_player_access_token(client):
    host = _create_four_player_match(client, is_private=True)
    code = host["room_code"]
    public_codes = [
        game["room_code"] for game in client.get("/spectator/live-games").json()
    ]
    assert code not in public_codes
    room_state = client.get(f"/rooms/{code}").json()
    assert host["spectator_token"] not in str(room_state)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/spectate/{code}") as spectator:
            spectator.send_json({"type": "SPECTATE"})
            spectator.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/spectate/{code}") as spectator:
            spectator.send_json({"type": "SPECTATE", "access_token": host["player_id"]})
            spectator.receive_json()

    with client.websocket_connect(f"/ws/spectate/{code}") as spectator:
        spectator.send_json({"type": "SPECTATE", "access_token": host["spectator_token"]})
        assert spectator.receive_json()["type"] == "SYNC_STATE"


def test_classic_spectators_are_read_only_and_counts_are_connection_based(client):
    white = client.post("/classic/rooms", json={
        "player_name": "White", "mode": "online", "is_private": False,
    }).json()
    black = client.post("/classic/rooms/join", json={
        "room_code": white["room_code"], "player_name": "Black",
    }).json()
    code = white["room_code"]
    assert client.post(f"/classic/rooms/{code}/start", json={
        "player_id": white["player_id"],
    }).status_code == 200

    with client.websocket_connect(f"/ws/spectate/classic/{code}") as first:
        first.send_json({"type": "SPECTATE"})
        sync = first.receive_json()
        assert sync["type"] == "SYNC_STATE"
        assert sync["game_mode"] == "classic"
        assert sync["game_state"]["turn"] == "white"
        assert "legal_moves" not in sync["game_state"]
        assert "player_id" not in str(sync)
        assert first.receive_json()["spectator_count"] == 1

        with client.websocket_connect(f"/ws/spectate/classic/{code}") as second:
            second.send_json({"type": "SPECTATE"})
            second_sync = second.receive_json()
            assert second_sync["spectator_count"] == 2
            assert second.receive_json()["spectator_count"] == 2
            assert first.receive_json()["spectator_count"] == 2
            second.send_json({"type": "PING"})
            timer = second.receive_json()
            assert timer["type"] == "PONG"
            assert timer["turn"] == "white"
            assert set(timer["clocks"]) == {"white", "black"}
            second.send_json({"type": "RESIGN"})
            assert second.receive_json()["type"] == "ERROR"

        assert first.receive_json()["spectator_count"] == 1

    with client.websocket_connect(f"/ws/classic/{code}") as player:
        player.send_json({"type": "AUTH", "player_id": white["player_id"]})
        player.receive_json()
        player.receive_json()
        player.send_json({"type": "MOVE", "from": "f2", "to": "f3"})
        assert player.receive_json()["type"] == "GAME_STATE"
    assert black["your_side"] == "black"


def test_private_classic_match_uses_separate_spectator_key(client):
    white = client.post("/classic/rooms", json={
        "player_name": "Private White", "mode": "online", "is_private": True,
    }).json()
    black = client.post("/classic/rooms/join", json={
        "room_code": white["room_code"], "player_name": "Private Black",
    }).json()
    code = white["room_code"]
    assert white["spectator_token"] == black["spectator_token"]
    classic_state = client.get(
        f"/classic/rooms/{code}",
        headers={"Authorization": f"Bearer {white['player_id']}"},
    ).json()
    assert white["spectator_token"] not in str(classic_state)
    assert client.post(f"/classic/rooms/{code}/start", json={
        "player_id": white["player_id"],
    }).status_code == 200
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/spectate/classic/{code}") as spectator:
            spectator.send_json({"type": "SPECTATE", "access_token": white["player_id"]})
            spectator.receive_json()
    with client.websocket_connect(f"/ws/spectate/classic/{code}") as spectator:
        spectator.send_json({"type": "SPECTATE", "access_token": white["spectator_token"]})
        assert spectator.receive_json()["type"] == "SYNC_STATE"


def test_completed_public_classic_match_has_verified_replay_positions(client):
    white = client.post("/classic/rooms", json={
        "player_name": "Replay White", "mode": "online", "is_private": False,
    }).json()
    black = client.post("/classic/rooms/join", json={
        "room_code": white["room_code"], "player_name": "Replay Black",
    }).json()
    code = white["room_code"]
    assert client.post(f"/classic/rooms/{code}/start", json={
        "player_id": white["player_id"],
    }).status_code == 200

    with client.websocket_connect(f"/ws/classic/{code}") as white_socket:
        white_socket.send_json({"type": "AUTH", "player_id": white["player_id"]})
        white_socket.receive_json()
        white_socket.receive_json()
        with client.websocket_connect(f"/ws/classic/{code}") as black_socket:
            black_socket.send_json({"type": "AUTH", "player_id": black["player_id"]})
            black_socket.receive_json()
            black_socket.receive_json()
            white_socket.receive_json()
            for socket, source, target in [
                (white_socket, "f2", "f3"),
                (black_socket, "e7", "e5"),
                (white_socket, "g2", "g4"),
                (black_socket, "d8", "h4"),
            ]:
                socket.send_json({"type": "MOVE", "from": source, "to": target})
                assert socket.receive_json()["type"] == "GAME_STATE"
                if source != "d8":
                    other = white_socket if socket is black_socket else black_socket
                    assert other.receive_json()["type"] == "GAME_STATE"

    matches = client.get("/spectator/replays").json()
    match = next(item for item in matches if item["room_code"] == code)
    replay_response = client.get(f"/spectator/replays/{match['match_id']}")
    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["result"] == "0-1"
    assert len(replay["positions"]) == 5
    assert replay["positions"][-1].split()[1] == "w"


def test_completed_public_four_player_match_replays_persisted_history(client):
    host = client.post("/rooms", json={
        "player_name": "Replay Host", "is_private": False,
    }).json()
    player_ids = [host["player_id"]]
    for seat in range(3):
        joined = client.post("/rooms/join", json={
            "room_code": host["room_code"], "player_name": f"Replay {seat + 2}",
        }).json()
        player_ids.append(joined["player_id"])
    code = host["room_code"]
    assert client.post(f"/rooms/{code}/start", json={
        "player_id": host["player_id"],
    }).status_code == 200
    for player_id in player_ids[:3]:
        assert client.post(f"/rooms/{code}/resign", json={
            "player_id": player_id,
        }).status_code == 200

    match = next(item for item in client.get("/spectator/replays").json()
                 if item["room_code"] == code)
    replay_response = client.get(f"/spectator/replays/{match['match_id']}")
    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["game_mode"] == "four_player"
    assert replay["result"] == "Player 4 wins"
    assert len(replay["positions"]) == 1


def test_spectators_are_closed_after_four_player_match_completion(client):
    host = client.post("/rooms", json={
        "player_name": "Completion Host", "is_private": False,
    }).json()
    player_ids = [host["player_id"]]
    for seat in range(3):
        joined = client.post("/rooms/join", json={
            "room_code": host["room_code"], "player_name": f"Finisher {seat + 2}",
        }).json()
        player_ids.append(joined["player_id"])
    code = host["room_code"]
    assert client.post(f"/rooms/{code}/start", json={
        "player_id": host["player_id"],
    }).status_code == 200

    from app.main import manager

    with client.websocket_connect(f"/ws/spectate/{code}") as spectator:
        spectator.send_json({"type": "SPECTATE"})
        spectator.receive_json()
        spectator.receive_json()
        for player_id in player_ids[:3]:
            assert client.post(f"/rooms/{code}/resign", json={
                "player_id": player_id,
            }).status_code == 200
            final_update = spectator.receive_json()
        assert final_update["type"] == "PLAYER_RESIGNED"
        assert final_update["is_game_over"] is True
        assert manager.spectator_count(code) == 0
