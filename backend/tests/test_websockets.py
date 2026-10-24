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

def test_websocket_sync_and_ping(client):
    # 1. Create a room
    res = client.post("/rooms", json={"player_name": "WS Player"})
    room = res.json()
    room_code = room["room_code"]
    player_id = room["player_id"]

    # 2. Connect WebSocket with player_id
    with client.websocket_connect(f"/ws/{room_code}?player_id={player_id}") as ws:
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
