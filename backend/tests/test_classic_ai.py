import threading
import time

import chess
import pytest
from fastapi.testclient import TestClient

import app.classic as classic_module
from app.classic_ai import DIFFICULTIES, choose_move
from app.db import init_db
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("difficulty", list(DIFFICULTIES))
def test_each_ai_difficulty_returns_a_legal_move(difficulty):
    board = chess.Board()
    move = choose_move(board, difficulty)
    assert move is not None
    assert move in board.legal_moves


@pytest.mark.parametrize(
    "fen",
    [
        "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1",
        "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
        "8/8/8/8/8/8/4k3/7K w - - 0 1",
    ],
)
def test_ai_returns_no_move_for_checkmate_stalemate_and_draw(fen):
    board = chess.Board(fen)
    assert board.is_game_over(claim_draw=True)
    assert choose_move(board, "expert") is None


def test_difficulty_levels_use_increasing_search_budgets():
    levels = [DIFFICULTIES[name] for name in (
        "beginner", "intermediate", "advanced", "expert",
    )]
    assert [level.depth for level in levels] == sorted(level.depth for level in levels)
    assert [level.max_nodes for level in levels] == sorted(level.max_nodes for level in levels)
    assert [level.think_seconds for level in levels] == sorted(
        level.think_seconds for level in levels
    )


def test_ai_room_creation_supports_both_player_sides(client):
    for human_side in ("white", "black"):
        response = client.post("/classic/rooms", json={
            "mode": "ai",
            "human_side": human_side,
            "ai_difficulty": "advanced",
            "time_control": "5+0",
            "player_name": "Human",
        })
        assert response.status_code == 200
        game = response.json()
        assert game["mode"] == "ai"
        assert game["your_side"] == human_side
        assert game["ai"]["human_side"] == human_side
        assert game["ai"]["difficulty"] == "advanced"
        assert len(game["players"]) == 2
        assert all("player_id" not in player for player in game["players"].values())


def test_ai_plays_after_human_move_and_respects_clock(client, monkeypatch):
    original_choose_move = classic_module.choose_move

    def deliberate_search(board, difficulty, cancel):
        time.sleep(0.2)
        return original_choose_move(board, difficulty, cancel)

    monkeypatch.setattr(classic_module, "choose_move", deliberate_search)
    created = client.post("/classic/rooms", json={
        "mode": "ai",
        "human_side": "white",
        "ai_difficulty": "beginner",
        "time_control": "1+0",
    }).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/classic/{code}") as socket:
        socket.send_json({"type": "AUTH", "player_id": created["player_id"]})
        assert socket.receive_json()["type"] == "SYNC_STATE"
        socket.receive_json()  # Presence broadcast
        socket.send_json({"type": "MOVE", "from": "e2", "to": "e4"})
        human_move = socket.receive_json()
        assert human_move["type"] == "GAME_STATE"
        thinking = socket.receive_json()
        assert thinking["type"] == "AI_THINKING"
        ai_move = socket.receive_json()
        assert ai_move["type"] == "GAME_STATE"
        assert ai_move["event"] == "AI_MOVE"
        assert ai_move["game_state"]["turn"] == "white"
        assert len(ai_move["game_state"]["moves"]) == 2
        assert ai_move["game_state"]["clocks"]["black"] < 60


def test_ai_white_opens_when_human_selects_black(client):
    created = client.post("/classic/rooms", json={
        "mode": "ai", "human_side": "black", "ai_difficulty": "beginner",
        "time_control": "unlimited",
    }).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/classic/{code}") as socket:
        socket.send_json({"type": "AUTH", "player_id": created["player_id"]})
        assert socket.receive_json()["type"] == "SYNC_STATE"
        socket.receive_json()  # Presence broadcast
        assert socket.receive_json()["type"] == "AI_THINKING"
        opened = socket.receive_json()
        assert opened["event"] == "AI_MOVE"
        assert opened["game_state"]["turn"] == "black"
        assert len(opened["game_state"]["moves"]) == 1


def test_restart_cancels_running_ai_search(client, monkeypatch):
    search_started = threading.Event()

    def wait_for_cancellation(board, difficulty, cancel):
        search_started.set()
        cancel.wait(2)
        return None

    monkeypatch.setattr(classic_module, "choose_move", wait_for_cancellation)
    created = client.post("/classic/rooms", json={
        "mode": "ai", "human_side": "white", "ai_difficulty": "expert",
        "time_control": "unlimited",
    }).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/classic/{code}") as socket:
        socket.send_json({"type": "AUTH", "player_id": created["player_id"]})
        socket.receive_json()  # Initial state
        socket.receive_json()  # Presence
        socket.send_json({"type": "MOVE", "from": "e2", "to": "e4"})
        socket.receive_json()  # Human move
        assert socket.receive_json()["type"] == "AI_THINKING"
        assert search_started.wait(1)
        restarted = client.post(
            f"/classic/rooms/{code}/restart",
            json={"player_id": created["player_id"]},
        )
        assert restarted.status_code == 200
        assert restarted.json()["game_state"]["fen"] == chess.STARTING_FEN
        assert restarted.json()["ai_thinking"] is False
        room_state = client.get(
            f"/classic/rooms/{code}",
            headers={"Authorization": f"Bearer {created['player_id']}"},
        ).json()
        assert room_state["game_state"]["moves"] == []


def test_resign_cancels_ai_and_finishes_game(client, monkeypatch):
    search_started = threading.Event()

    def wait_for_cancellation(board, difficulty, cancel):
        search_started.set()
        cancel.wait(2)
        return None

    monkeypatch.setattr(classic_module, "choose_move", wait_for_cancellation)
    created = client.post("/classic/rooms", json={
        "mode": "ai", "human_side": "black", "ai_difficulty": "expert",
        "time_control": "unlimited",
    }).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/classic/{code}") as socket:
        socket.send_json({"type": "AUTH", "player_id": created["player_id"]})
        socket.receive_json()  # Initial state
        socket.receive_json()  # Presence
        assert socket.receive_json()["type"] == "AI_THINKING"
        assert search_started.wait(1)
        resigned = client.post(
            f"/classic/rooms/{code}/resign",
            json={"player_id": created["player_id"]},
        )
        assert resigned.status_code == 200
        assert resigned.json()["game_state"]["termination"] == "resignation"
        assert resigned.json()["ai_thinking"] is False
