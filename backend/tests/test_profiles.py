import uuid
import secrets

import pytest
from fastapi.testclient import TestClient

from app.db import (
    MatchRecordModel,
    PlayerMatchModel,
    PlayerProfileModel,
    ProfileAchievementModel,
    SessionLocal,
    init_db,
)
from app.main import app
from app.profiles import _level_progress, classic_comeback, record_completed_match
from app.room_limits import _lock, _request_times


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_rate_limits():
    with _lock:
        _request_times.clear()
    yield
    with _lock:
        _request_times.clear()


def new_profile(client):
    response = client.post("/api/profile", json={})
    assert response.status_code == 200
    data = response.json()
    return data["access_token"], data["profile"]


def test_device_profile_creation_edit_validation_and_private_auth(client):
    token, profile = new_profile(client)
    auth = {"Authorization": f"Bearer {token}"}
    username = f"Player{secrets.randbelow(900000) + 100000}"
    assert profile["level"] == 1
    assert profile["ratings"] == {"classic": 1200, "four_player": 1200}
    assert client.get("/api/profile").status_code == 401

    updated = client.patch("/api/profile", headers=auth, json={
        "username": username,
        "avatar": "queen",
    })
    assert updated.status_code == 200
    assert updated.json()["username"] == username
    assert updated.json()["avatar"] == "queen"
    assert client.patch("/api/profile", headers=auth, json={"avatar": "https://evil.test"}).status_code == 422

    other_token, _ = new_profile(client)
    duplicate = client.patch("/api/profile", headers={"Authorization": f"Bearer {other_token}"}, json={
        "username": username.lower(),
    })
    assert duplicate.status_code == 409


def test_progression_level_thresholds_increase():
    assert _level_progress(99) == {
        "level": 1, "xp_into_level": 99, "xp_for_next_level": 100, "total_xp": 99,
    }
    assert _level_progress(100) == {
        "level": 2, "xp_into_level": 0, "xp_for_next_level": 200, "total_xp": 100,
    }
    assert _level_progress(300) == {
        "level": 3, "xp_into_level": 0, "xp_for_next_level": 300, "total_xp": 300,
    }
    assert _level_progress(600) == {
        "level": 4, "xp_into_level": 0, "xp_for_next_level": 400, "total_xp": 600,
    }


def test_comeback_achievement_uses_verified_classic_material_history():
    moves = [
        {"uci": move}
        for move in "e2e4 d7d5 e4d5 d8d5 b1c3 d5e5 c3e4 e5e4".split()
    ]
    assert classic_comeback(moves, "white")
    assert not classic_comeback(moves, "black")
    assert not classic_comeback([{"uci": "e2e5"}], "white")


def test_verified_classic_match_updates_elo_xp_history_and_is_idempotent(client):
    token_a, profile_a = new_profile(client)
    token_b, profile_b = new_profile(client)
    match_id = str(uuid.uuid4())
    with SessionLocal() as db:
        recorded = record_completed_match(
            db,
            match_id=match_id,
            room_code="TST123",
            game_mode="classic",
            started_at=None,
            moves=[{"uci": "e2e4", "san": "e4"}],
            participants=[
                {"profile_id": profile_a["id"], "username": profile_a["username"], "role": "white"},
                {"profile_id": profile_b["id"], "username": profile_b["username"], "role": "black"},
            ],
            winner_profile_id=profile_a["id"],
            is_draw=False,
            duration_seconds=42,
            rated=True,
        )
        assert recorded
        assert not record_completed_match(
            db,
            match_id=match_id,
            room_code="TST123",
            game_mode="classic",
            started_at=None,
            moves=[],
            participants=[],
            winner_profile_id=None,
            is_draw=True,
            duration_seconds=0,
            rated=True,
        )

    profile_a_now = client.get("/api/profile", headers={"Authorization": f"Bearer {token_a}"}).json()
    profile_b_now = client.get("/api/profile", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert profile_a_now["ratings"]["classic"] > 1200
    assert profile_b_now["ratings"]["classic"] < 1200
    assert profile_a_now["ratings"]["four_player"] == 1200
    assert profile_a_now["total_xp"] == 25
    assert profile_b_now["total_xp"] == 10
    assert "first_victory" in profile_a_now["achievements"]

    matches = client.get(
        "/api/profile/matches?game_mode=classic&result=win",
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()
    assert len(matches) == 1
    assert matches[0]["opponents"] == [profile_b["username"]]
    assert matches[0]["duration_seconds"] == 42
    assert matches[0]["moves"][0]["san"] == "e4"
    assert matches[0]["rated"] is True
    leaders = client.get("/api/leaderboard?game_mode=classic").json()
    assert any(row["username"] == profile_a["username"] for row in leaders)

    with SessionLocal() as db:
        assert db.query(MatchRecordModel).filter(MatchRecordModel.match_id == match_id).count() == 1
        assert db.query(PlayerMatchModel).filter(PlayerMatchModel.match_id == match_id).count() == 2
        assert db.query(ProfileAchievementModel).filter(
            ProfileAchievementModel.profile_id == profile_a["id"],
            ProfileAchievementModel.achievement_key == "first_victory",
        ).count() == 1


def test_four_player_rating_is_separate_and_draw_rewards_are_smaller(client):
    token_a, profile_a = new_profile(client)
    token_b, profile_b = new_profile(client)
    match_id = str(uuid.uuid4())
    with SessionLocal() as db:
        record_completed_match(
            db,
            match_id=match_id,
            room_code="TST124",
            game_mode="four_player",
            started_at=None,
            moves=[],
            participants=[
                {"profile_id": profile_a["id"], "username": profile_a["username"], "role": 1},
                {"profile_id": profile_b["id"], "username": profile_b["username"], "role": 2},
            ],
            winner_profile_id=profile_a["id"],
            is_draw=False,
            duration_seconds=0,
            rated=True,
        )
    a_data = client.get("/api/profile", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert a_data["ratings"]["classic"] == 1200
    assert a_data["ratings"]["four_player"] > 1200
    assert "four_player_champion" in a_data["achievements"]

    draw_id = str(uuid.uuid4())
    with SessionLocal() as db:
        record_completed_match(
            db,
            match_id=draw_id,
            room_code="TST125",
            game_mode="four_player",
            started_at=None,
            moves=[],
            participants=[
                {"profile_id": profile_a["id"], "username": profile_a["username"], "role": 1},
                {"profile_id": profile_b["id"], "username": profile_b["username"], "role": 2},
            ],
            winner_profile_id=None,
            is_draw=True,
            duration_seconds=0,
            rated=True,
        )
    a_after_draw = client.get("/api/profile", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert a_after_draw["statistics"]["draws"] == 1
    assert a_after_draw["total_xp"] == 40


def test_classic_draw_updates_stats_and_xp_without_rating_change(client):
    token_a, profile_a = new_profile(client)
    token_b, profile_b = new_profile(client)
    match_id = str(uuid.uuid4())
    with SessionLocal() as db:
        record_completed_match(
            db,
            match_id=match_id,
            room_code="TST126",
            game_mode="classic",
            started_at=None,
            moves=[],
            participants=[
                {"profile_id": profile_a["id"], "username": profile_a["username"], "role": "white"},
                {"profile_id": profile_b["id"], "username": profile_b["username"], "role": "black"},
            ],
            winner_profile_id=None,
            is_draw=True,
            duration_seconds=10,
            rated=True,
        )
    a_data = client.get("/api/profile", headers={"Authorization": f"Bearer {token_a}"}).json()
    b_data = client.get("/api/profile", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert a_data["statistics"]["draws"] == 1
    assert a_data["total_xp"] == 15
    assert a_data["ratings"]["classic"] == b_data["ratings"]["classic"] == 1200
    draw = client.get(
        "/api/profile/matches?result=draw",
        headers={"Authorization": f"Bearer {token_a}"},
    ).json()[0]
    assert draw["rating_delta"] == 0
    assert draw["rated"] is True


def test_ten_verified_wins_unlock_count_and_streak_achievements(client):
    token_a, profile_a = new_profile(client)
    _, profile_b = new_profile(client)
    with SessionLocal() as db:
        for index in range(10):
            record_completed_match(
                db,
                match_id=str(uuid.uuid4()),
                room_code=f"R{index:05}",
                game_mode="classic",
                started_at=None,
                moves=[],
                participants=[
                    {"profile_id": profile_a["id"], "username": profile_a["username"], "role": "white"},
                    {"profile_id": profile_b["id"], "username": profile_b["username"], "role": "black"},
                ],
                winner_profile_id=profile_a["id"],
                is_draw=False,
                duration_seconds=60,
                rated=True,
            )
    data = client.get("/api/profile", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert data["statistics"]["games"] == 10
    assert data["statistics"]["wins"] == 10
    assert data["statistics"]["current_streak"] == 10
    assert {"ten_games", "ten_wins", "five_streak"}.issubset(data["achievements"])


def test_profile_is_linked_to_rooms_and_abandoned_ai_game_is_not_recorded(client):
    token, profile = new_profile(client)
    auth = {"Authorization": f"Bearer {token}"}
    room = client.post("/rooms", headers=auth, json={"player_name": "Ignored"}).json()
    assert room["player_name"] == profile["username"]
    duplicate = client.post("/rooms/join", headers=auth, json={
        "room_code": room["room_code"], "player_name": "Another seat",
    })
    assert duplicate.status_code == 409

    abandoned = client.post("/classic/rooms", headers=auth, json={
        "mode": "ai", "time_control": "unlimited",
    })
    assert abandoned.status_code == 200
    abandoned = abandoned.json()
    assert abandoned["players"]["white"]["name"] == profile["username"]
    history = client.get("/api/profile/matches", headers=auth).json()
    assert all(match["room_code"] != abandoned["room_code"] for match in history)

    finished = client.post("/classic/rooms", headers=auth, json={
        "mode": "ai", "time_control": "unlimited",
    }).json()
    resigned = client.post(
        f"/classic/rooms/{finished['room_code']}/resign",
        headers=auth,
        json={"player_id": finished["player_id"]},
    )
    assert resigned.status_code == 200
    history = client.get("/api/profile/matches", headers=auth).json()
    completed = next(row for row in history if row["room_code"] == finished["room_code"])
    assert completed["result"] == "loss"
    assert completed["xp_awarded"] == 10
    assert all(row["room_code"] != abandoned["room_code"] for row in history)


def test_four_player_authoritative_completion_records_rating_and_achievement(client):
    identities = [new_profile(client) for _ in range(4)]
    host_token, host = identities[0]
    host_auth = {"Authorization": f"Bearer {host_token}"}
    room = client.post("/rooms", headers=host_auth, json={"player_name": "Host"}).json()
    player_ids = [room["player_id"]]
    for token, _profile in identities[1:]:
        joined = client.post(
            "/rooms/join",
            headers={"Authorization": f"Bearer {token}"},
            json={"room_code": room["room_code"], "player_name": "Guest"},
        )
        assert joined.status_code == 200
        player_ids.append(joined.json()["player_id"])
    assert client.post(
        f"/rooms/{room['room_code']}/start",
        json={"player_id": player_ids[0]},
    ).status_code == 200
    for player_id in player_ids[:3]:
        response = client.post(
            f"/rooms/{room['room_code']}/resign",
            json={"player_id": player_id},
        )
        assert response.status_code == 200

    winner_token, winner = identities[3]
    result = client.get(
        "/api/profile",
        headers={"Authorization": f"Bearer {winner_token}"},
    ).json()
    assert result["statistics"]["wins"] == 1
    assert result["ratings"]["four_player"] > 1200
    assert result["ratings"]["classic"] == 1200
    assert "four_player_champion" in result["achievements"]
    history = client.get(
        "/api/profile/matches?game_mode=four_player",
        headers={"Authorization": f"Bearer {winner_token}"},
    ).json()
    assert history[0]["result"] == "win"
    assert len(history[0]["opponents"]) == 3
