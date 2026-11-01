import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import profiles
from app.db import (
    DailyPuzzleModel,
    PlayerPuzzleAttemptModel,
    PlayerPuzzleProgressModel,
    SessionLocal,
    init_db,
)
from app.main import app
from app.room_limits import _lock, _request_times
from app.profiles import _next_puzzle_streak, _timezone_for


PUZZLE_SOURCE = {
    "game": {
        "id": "7J4rhbpE",
        "pgn": "e4 c6 d4 d5 exd5 cxd5 c4 Nc6 Nc3 Nf6 Bg5 Bg4 Nf3 e6 Be2 Bxf3 "
        "Bxf3 Be7 cxd5 Nxd5 Nxd5 Bxg5 Nc3 Qxd4 Qxd4 Nxd4 Bxb7 Rb8 Be4 f5 "
        "Bd3 Rxb2 O-O O-O Bc4 Kh8 Bb3 Ne2+ Nxe2 Rxe2 Rad1 e5 Rd7 Rd8 Rxa7 "
        "h5 g3 Rdd2 Rf7 Bf6 Rf8+ Kh7 Bg8+ Kh6 Bf7 f4",
    },
    "puzzle": {
        "id": "fWQJU",
        "rating": 1942,
        "themes": ["endgame", "long", "mateIn3"],
        "fen": "5R2/5Bp1/5b1k/4p2p/5p2/6P1/P2rrP1P/5RK1 w - - 0 1",
        "solution": ["f8h8", "h6g5", "h8h5", "g5g4", "f2f3"],
    },
}


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(profiles, "_fetch_lichess_daily", lambda: PUZZLE_SOURCE)
    with _lock:
        _request_times.clear()
    yield TestClient(app)
    with _lock:
        _request_times.clear()


def new_profile(client, timezone_name="UTC"):
    response = client.post("/api/profile", json={"timezone": timezone_name})
    assert response.status_code == 200
    data = response.json()
    return data["access_token"], data["profile"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_sourced_daily_puzzle_is_legal_and_does_not_expose_solution(client):
    token, _profile = new_profile(client)
    response = client.get("/api/puzzles/daily", headers=auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["puzzle_id"] == "fWQJU"
    assert data["difficulty"] == "hard"
    assert data["objective"] == "Find the forced checkmate in 3."
    assert data["source_url"] == "https://lichess.org/training/fWQJU"
    assert "solution" not in data
    assert data["progress"]["current_streak"] == 0
    with SessionLocal() as db:
        puzzle = db.query(DailyPuzzleModel).filter_by(puzzle_id="fWQJU").one()
        import chess

        board = chess.Board(puzzle.fen)
        assert board.is_valid()
        for move in json.loads(puzzle.solution_json)[0]:
            assert chess.Move.from_uci(move) in board.legal_moves
            board.push_uci(move)
        assert board.is_checkmate()


def test_daily_solution_feedback_hints_reset_reward_and_duplicate_prevention(client):
    token, _profile = new_profile(client)
    headers = auth(token)
    puzzle = client.get("/api/puzzles/daily", headers=headers).json()
    hint = client.post(
        "/api/puzzles/daily/hint",
        headers=headers,
        json={"puzzle_id": puzzle["puzzle_id"]},
    )
    assert hint.status_code == 200
    assert "rook" in hint.json()["hint"]

    wrong = client.post(
        "/api/puzzles/daily/move",
        headers=headers,
        json={"puzzle_id": puzzle["puzzle_id"], "move": "a2a3"},
    )
    assert wrong.status_code == 200
    assert wrong.json()["correct"] is False
    assert wrong.json()["incorrect_attempts"] == 1
    illegal = client.post(
        "/api/puzzles/daily/move",
        headers=headers,
        json={"puzzle_id": puzzle["puzzle_id"], "move": "a2a5"},
    )
    assert illegal.status_code == 422

    reset = client.post(
        "/api/puzzles/daily/reset",
        headers=headers,
        json={"puzzle_id": puzzle["puzzle_id"]},
    )
    assert reset.status_code == 200
    saved = client.get("/api/puzzles/daily", headers=headers).json()["attempt"]
    assert saved["moves"] == []
    assert saved["incorrect_attempts"] == 1
    assert saved["hint_count"] == 1

    moves = ["f8h8", "h8h5", "f2f3"]
    for index, move in enumerate(moves):
        result = client.post(
            "/api/puzzles/daily/move",
            headers=headers,
            json={"puzzle_id": puzzle["puzzle_id"], "move": move},
        )
        assert result.status_code == 200
        assert result.json()["correct"] is True
        assert result.json()["completed"] is (index == len(moves) - 1)
    completed = result.json()
    assert completed["xp_awarded"] == 20
    assert "Rh8+" in completed["explanation"]
    assert completed["progress"]["current_streak"] == 1
    assert completed["progress"]["total_completed"] == 1
    assert completed["progress"]["accuracy"] == 0
    assert client.get("/api/profile", headers=headers).json()["total_xp"] == 20

    duplicate = client.post(
        "/api/puzzles/daily/move",
        headers=headers,
        json={"puzzle_id": puzzle["puzzle_id"], "move": "f2f3"},
    )
    assert duplicate.status_code == 409
    assert client.get("/api/profile", headers=headers).json()["total_xp"] == 20


def test_first_attempt_bonus_and_archive_replay_do_not_award_xp(client):
    token, _profile = new_profile(client)
    headers = auth(token)
    puzzle = client.get("/api/puzzles/daily", headers=headers).json()
    for move in ["f8h8", "h8h5", "f2f3"]:
        result = client.post(
            "/api/puzzles/daily/move",
            headers=headers,
            json={"puzzle_id": puzzle["puzzle_id"], "move": move},
        )
        assert result.status_code == 200
    assert result.json()["xp_awarded"] == 25
    assert result.json()["first_attempt_correct"] is True
    username = client.get("/api/profile", headers=headers).json()["username"]
    leaderboard = client.get(
        f"/api/leaderboard?game_mode=all&category=xp&search={username}",
        headers=headers,
    ).json()
    assert leaderboard["entries"][0]["score"] == 25

    archive = client.get("/api/puzzles/archive?difficulty=hard", headers=headers)
    assert archive.status_code == 200
    assert archive.json()["total"] == 1
    assert archive.json()["entries"][0]["completed"] is True
    archived = client.get(
        f"/api/puzzles/archive/{puzzle['puzzle_id']}",
        headers=headers,
    )
    assert archived.status_code == 200
    assert archived.json()["practice_only"] is True
    accepted_moves = []
    for move in ["f8h8", "h8h5", "f2f3"]:
        response = client.post(
            f"/api/puzzles/archive/{puzzle['puzzle_id']}/move",
            headers=headers,
            json={"move": move, "moves": accepted_moves},
        )
        assert response.status_code == 200
        assert response.json()["correct"] is True
        accepted_moves = response.json()["moves"]
    assert response.json()["completed"] is True
    assert client.get("/api/profile", headers=headers).json()["total_xp"] == 25
    with SessionLocal() as db:
        progress = db.query(PlayerPuzzleProgressModel).filter_by(
            profile_id=client.get("/api/profile", headers=headers).json()["id"]
        ).one()
        assert progress.total_completed == 1
        assert db.query(PlayerPuzzleAttemptModel).count() >= 1


def test_timezone_controls_local_day_and_locks_after_daily_attempt(client):
    timezone_name = "America/Los_Angeles"
    token, profile = new_profile(client, timezone_name)
    headers = auth(token)
    daily = client.get("/api/puzzles/daily", headers=headers)
    assert daily.status_code == 200
    expected_date = datetime.now(timezone.utc).astimezone(
        profiles._timezone_for(timezone_name)
    ).date().isoformat()
    assert daily.json()["challenge_date"] == expected_date
    assert profile["timezone"] == timezone_name
    changed = client.patch(
        "/api/profile",
        headers=headers,
        json={"timezone": "UTC"},
    )
    assert changed.status_code == 200
    assert changed.json()["timezone"] == "UTC"
    daily = client.get("/api/puzzles/daily", headers=headers).json()
    started = client.post(
        "/api/puzzles/daily/hint",
        headers=headers,
        json={"puzzle_id": daily["puzzle_id"]},
    )
    assert started.status_code == 200
    locked = client.patch(
        "/api/profile",
        headers=headers,
        json={"timezone": timezone_name},
    )
    assert locked.status_code == 409
    invalid = client.patch(
        "/api/profile",
        headers=headers,
        json={"timezone": "Not/AZone"},
    )
    assert invalid.status_code == 422


def test_streak_uses_local_calendar_days_across_daylight_saving_transition():
    new_york = _timezone_for("America/New_York")
    before_fallback = datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).astimezone(new_york)
    after_fallback = datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc).astimezone(new_york)
    next_local_day = datetime(2026, 11, 2, 5, 30, tzinfo=timezone.utc).astimezone(new_york)
    assert before_fallback.fold == 0
    assert after_fallback.fold == 1
    assert before_fallback.date() == after_fallback.date()
    assert _next_puzzle_streak(1, 1, "2026-11-01", next_local_day.date().isoformat()) == (2, 2)


def test_invalid_source_position_is_rejected(client, monkeypatch):
    token, _profile = new_profile(client)
    class FutureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(days=3650)

    monkeypatch.setattr(profiles, "datetime", FutureDateTime)
    invalid_source = {
        **PUZZLE_SOURCE,
        "puzzle": {**PUZZLE_SOURCE["puzzle"], "fen": "not a FEN"},
    }
    monkeypatch.setattr(profiles, "_fetch_lichess_daily", lambda: invalid_source)
    response = client.get("/api/puzzles/daily", headers=auth(token))
    assert response.status_code == 502


def test_unauthenticated_puzzle_actions_are_rejected(client):
    assert client.get("/api/puzzles/daily").status_code == 401
    assert client.get("/api/puzzles/archive").status_code == 401
