import chess
import pytest
from app.classic import (
    classic_rooms, create_classic_room, _public_state,
    CreateClassicRoomRequest, ClassicGame
)
from app.db import SessionLocal, init_db
from app.room_limits import _lock, _request_times
from starlette.requests import Request


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()


@pytest.fixture(autouse=True)
def clear_rate_limits():
    with _lock:
        _request_times.clear()


@pytest.fixture
def fake_request():
    return Request({"type": "http", "client": ("127.0.0.1", 54321), "headers": []})


def test_classic_local_match_lifecycle_and_moves(fake_request):
    db = SessionLocal()
    try:
        req = CreateClassicRoomRequest(mode="local", time_control="unlimited", player_name="SoloPlayer")
        created = create_classic_room(req, fake_request, db)
        code = created["room_code"]

        assert created["status"] == "PLAYING"
        assert created["game_state"]["status"] == "PLAYING"
        assert created["game_state"]["turn"] == "white"
        assert created["game_state"]["fen"] == chess.STARTING_FEN

        room = classic_rooms[code]
        assert room["status"] == "PLAYING"

        # White moves e2 -> e4
        room["game"].play("e2", "e4", None)
        state1 = _public_state(code, room)
        assert state1["game_state"]["turn"] == "black"
        assert state1["game_state"]["moves"][-1]["uci"] == "e2e4"

        # Black moves e7 -> e5
        room["game"].play("e7", "e5", None)
        state2 = _public_state(code, room)
        assert state2["game_state"]["turn"] == "white"
        assert len(state2["game_state"]["moves"]) == 2
        assert state2["game_state"]["moves"][-1]["uci"] == "e7e5"
    finally:
        db.close()


def test_classic_online_match_lifecycle_waiting_to_start(fake_request):
    db = SessionLocal()
    try:
        # 1. Host creates room
        host_req = CreateClassicRoomRequest(mode="online", time_control="10+0", player_name="Alice")
        created = create_classic_room(host_req, fake_request, db)
        code = created["room_code"]

        # MUST be WAITING upon creation
        assert created["status"] == "WAITING"
        assert created["game_state"]["status"] == "WAITING"

        room = classic_rooms[code]
        assert room["status"] == "WAITING"

        # 2. Simulate second player joined
        room["players"]["black"] = {
            "player_id": "player-2-id",
            "name": "Bob",
            "connected": True,
            "ready": True,
            "host": False,
        }

        # Room status MUST remain WAITING until host explicitly starts match
        waiting_state = _public_state(code, room)
        assert waiting_state["status"] == "WAITING"
        assert waiting_state["game_state"]["status"] == "WAITING"
        assert len(waiting_state["players"]) == 2

        # 3. Host starts match
        room["status"] = "PLAYING"
        started_state = _public_state(code, room)
        assert started_state["status"] == "PLAYING"
        assert started_state["game_state"]["status"] == "PLAYING"
        assert started_state["game_state"]["turn"] == "white"

        # 4. Players make valid moves: e2 -> e4, then e7 -> e5
        room["game"].play("e2", "e4", None)
        assert room["game"].board.turn is False  # Black's turn
        room["game"].play("e7", "e5", None)
        assert room["game"].board.turn is True  # White's turn
        assert len(room["game"].moves) == 2
        assert room["game"].moves[0]["uci"] == "e2e4"
        assert room["game"].moves[1]["san"] == "e5"
    finally:
        db.close()


def test_classic_ai_match_lifecycle_starts_playing_immediately(fake_request):
    db = SessionLocal()
    try:
        req = CreateClassicRoomRequest(
            mode="ai", time_control="10+0", player_name="Human",
            human_side="white", ai_difficulty="intermediate"
        )
        created = create_classic_room(req, fake_request, db)
        code = created["room_code"]

        assert created["status"] == "PLAYING"
        assert created["game_state"]["status"] == "PLAYING"
        assert created["game_state"]["turn"] == "white"

        room = classic_rooms[code]
        assert room["status"] == "PLAYING"
        assert room["started_at"] is not None
        assert room["game"].clock_started_at is not None

        # Human makes move e2 -> e4
        room["game"].play("e2", "e4", None)
        assert room["game"].board.turn is False  # AI's turn
        assert room["game"].moves[0]["uci"] == "e2e4"
    finally:
        db.close()
