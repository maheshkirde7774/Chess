import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["service"] == "FOURX"

def test_create_and_join_room_flow(client):
    # 1. Create Room (Player 1 - Cyan)
    res1 = client.post("/rooms", json={"player_name": "Alice"})
    assert res1.status_code == 200
    p1 = res1.json()
    room_code = p1["room_code"]
    assert len(room_code) == 6
    assert p1["player_role"] == 1
    assert p1["player_name"] == "Alice"
    p1_id = p1["player_id"]

    # 2. Join Player 2 (Magenta)
    res2 = client.post("/rooms/join", json={"room_code": room_code, "player_name": "Bob"})
    assert res2.status_code == 200
    p2 = res2.json()
    assert p2["player_role"] == 2
    assert p2["player_name"] == "Bob"
    p2_id = p2["player_id"]

    # 3. Join Player 3 (Lime)
    res3 = client.post("/rooms/join", json={"room_code": room_code, "player_name": "Charlie"})
    assert res3.status_code == 200
    p3 = res3.json()
    assert p3["player_role"] == 3

    # 4. Join Player 4 (Gold)
    res4 = client.post("/rooms/join", json={"room_code": room_code, "player_name": "Diana"})
    assert res4.status_code == 200
    p4 = res4.json()
    assert p4["player_role"] == 4

    # 5. Attempt 5th join -> should fail with 400 Room is full
    res5 = client.post("/rooms/join", json={"room_code": room_code, "player_name": "Eve"})
    assert res5.status_code == 400
    assert "full" in res5.json()["detail"].lower()

    assert client.get(f"/rooms/{room_code}").json()["status"] == "WAITING"
    assert client.post(f"/rooms/{room_code}/start", json={"player_id": p2_id}).status_code == 403
    started = client.post(f"/rooms/{room_code}/start", json={"player_id": p1_id})
    assert started.status_code == 200

    # 6. Check room state
    state_res = client.get(f"/rooms/{room_code}")
    assert state_res.status_code == 200
    s_data = state_res.json()
    assert s_data["room_code"] == room_code
    assert s_data["status"] == "PLAYING"
    assert len(s_data["players"]) == 4
    assert s_data["current_turn"] == 1

def test_server_authoritative_move_validation(client):
    # Create room with 4 players
    res1 = client.post("/rooms", json={"player_name": "P1"})
    p1 = res1.json()
    room_code = p1["room_code"]
    p1_id = p1["player_id"]

    res2 = client.post("/rooms/join", json={"room_code": room_code, "player_name": "P2"})
    p2 = res2.json()
    p2_id = p2["player_id"]
    client.post("/rooms/join", json={"room_code": room_code, "player_name": "P3"})
    client.post("/rooms/join", json={"room_code": room_code, "player_name": "P4"})
    assert client.post(f"/rooms/{room_code}/start", json={"player_id": p1_id}).status_code == 200

    # Player 2 tries to move out of turn -> Should be 403 Forbidden
    bad_turn_move = client.post(f"/rooms/{room_code}/move", json={
        "player_id": p2_id,
        "from_sq": [6, 1],
        "to_sq": [6, 3]
    })
    assert bad_turn_move.status_code == 403
    assert "not your turn" in bad_turn_move.json()["detail"].lower()

    # Fake invalid player ID -> 403 Unauthorized
    fake_move = client.post(f"/rooms/{room_code}/move", json={
        "player_id": "invalid-uuid-token",
        "from_sq": [12, 6],
        "to_sq": [10, 6]
    })
    assert fake_move.status_code == 403

    # Player 1 attempts illegal piece move -> 400 Bad Request
    illegal_move = client.post(f"/rooms/{room_code}/move", json={
        "player_id": p1_id,
        "from_sq": [12, 6],
        "to_sq": [9, 6]  # Pawns cannot move 3 squares
    })
    assert illegal_move.status_code == 400

    # Player 1 makes valid move -> 200 OK
    valid_move = client.post(f"/rooms/{room_code}/move", json={
        "player_id": p1_id,
        "from_sq": [12, 6],
        "to_sq": [10, 6]
    })
    assert valid_move.status_code == 200
    res_data = valid_move.json()
    assert res_data["success"] is True
    assert res_data["state"]["current_turn"] == 2  # Turn passed to Player 2 (Magenta)

def test_resign_flow(client):
    res1 = client.post("/rooms", json={"player_name": "P1"})
    p1 = res1.json()
    room_code = p1["room_code"]
    p1_id = p1["player_id"]
    for name in ("P2", "P3", "P4"):
        assert client.post("/rooms/join", json={"room_code": room_code, "player_name": name}).status_code == 200
    assert client.post(f"/rooms/{room_code}/start", json={"player_id": p1_id}).status_code == 200

    # Player 1 resigns
    res_resign = client.post(f"/rooms/{room_code}/resign", json={"player_id": p1_id})
    assert res_resign.status_code == 200
    assert res_resign.json()["success"] is True

    # Room state check
    state_res = client.get(f"/rooms/{room_code}")
    s_data = state_res.json()
    assert 1 in s_data["game_state"]["eliminated_players"]

def test_room_settings_public_discovery_and_leave_transfer(client):
    created = client.post("/rooms", json={
        "player_name": "Host", "is_private": False, "time_control": "5+0",
    })
    assert created.status_code == 200
    host = created.json()
    code = host["room_code"]
    assert len(host["player_id"]) >= 40
    state = client.get(f"/rooms/{code}").json()
    assert state["settings"] == {
        "game_mode": "four_player",
        "is_private": False,
        "time_control": "5+0",
        "max_players": 4,
    }
    assert "player_id" not in str(state["players"])
    assert code in [room["room_code"] for room in client.get("/rooms").json()]

    guest = client.post("/rooms/join", json={"room_code": code, "player_name": "Guest"}).json()
    assert guest["player_role"] == 2
    assert client.post(f"/rooms/{code}/leave", json={"player_id": host["player_id"]}).status_code == 200
    updated = client.get(f"/rooms/{code}").json()
    assert updated["host_role"] == 2
    assert "1" not in updated["players"]
    assert client.post(f"/rooms/{code}/leave", json={"player_id": guest["player_id"]}).status_code == 200
    assert client.get(f"/rooms/{code}").status_code == 404

def test_invalid_room_code_and_waiting_action_rejected(client):
    created = client.post("/rooms", json={"player_name": "Host"}).json()
    code = created["room_code"]
    assert client.post("/rooms/join", json={"room_code": "bad!"}).status_code == 422
    assert client.post(f"/rooms/{code}/start", json={"player_id": created["player_id"]}).status_code == 400
    assert client.post(f"/rooms/{code}/move", json={
        "player_id": created["player_id"], "from_sq": [12, 6], "to_sq": [10, 6],
    }).status_code == 400
    assert client.post(f"/rooms/{code}/reset", json={"player_id": created["player_id"]}).status_code == 200
    assert client.get(f"/rooms/{code}").json()["status"] == "WAITING"
