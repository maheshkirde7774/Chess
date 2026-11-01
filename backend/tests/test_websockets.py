import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
from app.db import init_db

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()

@pytest.fixture
def client():
    return TestClient(app)

def test_websocket_sync_and_ping(client):
    # 1. Create a room
    res = client.post("/rooms", json={"player_name": "WS Player"})
    room = res.json()
    room_code = room["room_code"]
    player_id = room["player_id"]
    for name in ("Player 2", "Player 3", "Player 4"):
        assert client.post("/rooms/join", json={"room_code": room_code, "player_name": name}).status_code == 200
    assert client.post(f"/rooms/{room_code}/start", json={"player_id": player_id}).status_code == 200

    # 2. Connect WebSocket with player_id
    with client.websocket_connect(f"/ws/{room_code}") as ws:
        ws.send_json({"type": "AUTH", "player_id": player_id})
        # Receive SYNC_STATE frame
        sync_msg = ws.receive_json()
        assert sync_msg["type"] == "SYNC_STATE"
        assert sync_msg["room_code"] == room_code
        assert sync_msg["your_role"] == 1
        assert "game_state" in sync_msg

        # Receive PRESENCE_UPDATE broadcast
        presence_msg = ws.receive_json()
        assert presence_msg["type"] == "PRESENCE_UPDATE"
        assert presence_msg["role"] == 1

        # Send PING frame
        ws.send_json({"type": "PING"})
        pong_msg = ws.receive_json()
        assert pong_msg["type"] == "PONG"

        # Send a valid move via WS
        ws.send_json({
            "type": "MOVE",
            "from": [12, 6],
            "to": [10, 6]
        })
        move_msg = ws.receive_json()
        assert move_msg["type"] == "MOVE_MADE"
        assert move_msg["player"] == 1
        assert move_msg["game_state"]["current_turn"] == 2


def test_websocket_host_start_validation_and_state_reconnection(client):
    host = client.post("/rooms", json={"player_name": "Host"}).json()
    code = host["room_code"]
    for seat in range(2, 5):
        joined = client.post("/rooms/join", json={
            "room_code": code, "player_name": f"Player {seat}",
        })
        assert joined.status_code == 200
        assert joined.json()["player_role"] == seat

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/{code}") as socket:
            socket.send_json({"type": "AUTH", "player_id": "not-a-player"})
            socket.receive_json()

    with client.websocket_connect(f"/ws/{code}") as socket:
        socket.send_json({"type": "AUTH", "player_id": host["player_id"]})
        initial = socket.receive_json()
        assert initial["status"] == "WAITING"
        assert "player_id" not in str(initial["players"])
        socket.receive_json()  # Host presence
        socket.send_json({"type": "START_GAME"})
        started = socket.receive_json()
        assert started["type"] == "GAME_STARTED"
        socket.send_json({"type": "MOVE", "from": "invalid", "to": [10, 6]})
        assert socket.receive_json()["type"] == "ERROR"
        socket.send_json({"type": "MOVE", "from": [12, 6], "to": [10, 6]})
        move = socket.receive_json()
        assert move["type"] == "MOVE_MADE"
        assert move["game_state"]["current_turn"] == 2

    from app.main import active_rooms
    active_rooms.pop(code)
    restored = client.get(f"/rooms/{code}")
    assert restored.status_code == 200
    assert restored.json()["current_turn"] == 2
    with client.websocket_connect(f"/ws/{code}") as socket:
        socket.send_json({"type": "AUTH", "player_id": host["player_id"]})
        sync = socket.receive_json()
        assert sync["type"] == "SYNC_STATE"
        assert sync["game_state"]["current_turn"] == 2
        socket.receive_json()  # Reconnected presence
