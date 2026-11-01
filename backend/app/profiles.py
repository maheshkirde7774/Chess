"""Device-scoped player profiles, progression, ratings, and verified match history."""

import hashlib
import json
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import chess
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import (
    MatchRecordModel,
    PlayerMatchModel,
    PlayerProfileModel,
    ProfileAchievementModel,
    get_db,
)
from app.room_limits import enforce_room_rate_limit

router = APIRouter()
_leaderboard_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_leaderboard_cache_lock = threading.Lock()
LEADERBOARD_CACHE_SECONDS = 30

AVATARS = {"king", "queen", "rook", "bishop", "knight", "pawn"}
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Optional[str] = Field(default=None, min_length=3, max_length=20)
    avatar: Optional[str] = Field(default=None, max_length=16)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _authenticated_profile(
    authorization: Optional[str],
    db: Session,
) -> PlayerProfileModel:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="A device profile credential is required")
    token = authorization[7:]
    if len(token) < 40 or len(token) > 160:
        raise HTTPException(status_code=401, detail="Invalid profile credential")
    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.token_hash == _token_hash(token)
    ).first()
    if profile is None:
        raise HTTPException(status_code=401, detail="Invalid profile credential")
    if profile.is_suspended or profile.deleted_at is not None:
        raise HTTPException(status_code=403, detail="This profile is unavailable")
    return profile


def _invalidate_leaderboard_cache() -> None:
    with _leaderboard_cache_lock:
        _leaderboard_cache.clear()


def profile_from_authorization(authorization: Optional[str], db: Session) -> Optional[PlayerProfileModel]:
    """Resolve an optional profile bearer token for game room attribution."""
    if authorization is None:
        return None
    return _authenticated_profile(authorization, db)


def _level_progress(xp: int) -> dict[str, int]:
    level = 1
    remaining = max(0, xp)
    requirement = level * 100
    while remaining >= requirement:
        remaining -= requirement
        level += 1
        requirement = level * 100
    return {
        "level": level,
        "xp_into_level": remaining,
        "xp_for_next_level": requirement,
        "total_xp": max(0, xp),
    }


def _profile_payload(db: Session, profile: PlayerProfileModel) -> dict[str, Any]:
    stats = db.query(
        func.count(PlayerMatchModel.id),
        func.coalesce(func.sum(case((PlayerMatchModel.result == "win", 1), else_=0)), 0),
        func.coalesce(func.sum(case((PlayerMatchModel.result == "loss", 1), else_=0)), 0),
        func.coalesce(func.sum(case((PlayerMatchModel.result == "draw", 1), else_=0)), 0),
    ).filter(PlayerMatchModel.profile_id == profile.id).one()
    total, wins, losses, draws = stats
    achievements = db.query(ProfileAchievementModel).filter(
        ProfileAchievementModel.profile_id == profile.id
    ).all()
    return {
        "id": profile.id,
        "username": profile.username,
        "avatar": profile.avatar,
        "joined_at": profile.created_at.isoformat() if profile.created_at else None,
        **_level_progress(profile.xp),
        "ratings": {
            "classic": profile.classic_rating,
            "four_player": profile.four_player_rating,
        },
        "statistics": {
            "games": total,
            "wins": wins,
            "losses": losses,
            "draws": draws,
            "win_percentage": round(wins * 100 / total, 1) if total else 0,
            "current_streak": profile.current_streak,
            "best_streak": profile.best_streak,
        },
        "achievements": sorted(achievement.achievement_key for achievement in achievements),
    }


@router.post("/api/profile")
def create_device_profile(
    request: Request,
    db: Session = Depends(get_db),
):
    """Creates an anonymous device profile; its bearer secret is returned only once."""
    enforce_room_rate_limit(request, "profile-create", limit=30)
    token = secrets.token_urlsafe(48)
    suffix = secrets.randbelow(900_000) + 100_000
    username = f"Commander{suffix}"
    profile = PlayerProfileModel(
        id=str(uuid.uuid4()),
        username=username,
        username_key=username.casefold(),
        avatar="knight",
        token_hash=_token_hash(token),
        created_at=datetime.now(timezone.utc),
        xp=0,
        classic_rating=1200,
        four_player_rating=1200,
    )
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Could not create a unique profile; please retry")
    _invalidate_leaderboard_cache()
    return {"access_token": token, "profile": _profile_payload(db, profile)}


@router.get("/api/profile")
def get_profile(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    return _profile_payload(db, profile)


@router.patch("/api/profile")
def update_profile(
    update: ProfileUpdate,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    if update.username is None and update.avatar is None:
        raise HTTPException(status_code=422, detail="Provide a username or avatar to update")
    if update.username is not None:
        username = update.username.strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
            raise HTTPException(status_code=422, detail="Username must be 3-20 letters, numbers, or underscores")
        key = username.casefold()
        duplicate = db.query(PlayerProfileModel).filter(
            PlayerProfileModel.username_key == key,
            PlayerProfileModel.id != profile.id,
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="That username is already taken")
        profile.username = username
        profile.username_key = key
    if update.avatar is not None:
        if update.avatar not in AVATARS:
            raise HTTPException(status_code=422, detail="Select an available avatar")
        profile.avatar = update.avatar
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username is already taken")
    db.refresh(profile)
    _invalidate_leaderboard_cache()
    return _profile_payload(db, profile)


@router.get("/api/profile/matches")
def profile_matches(
    game_mode: Optional[str] = None,
    result: Optional[str] = None,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    if game_mode not in (None, "classic", "four_player"):
        raise HTTPException(status_code=422, detail="Unsupported game mode filter")
    if result not in (None, "win", "loss", "draw"):
        raise HTTPException(status_code=422, detail="Unsupported result filter")
    query = db.query(PlayerMatchModel, MatchRecordModel).join(
        MatchRecordModel, PlayerMatchModel.match_id == MatchRecordModel.match_id
    ).filter(PlayerMatchModel.profile_id == profile.id)
    if game_mode:
        query = query.filter(MatchRecordModel.game_mode == game_mode)
    if result:
        query = query.filter(PlayerMatchModel.result == result)
    rows = query.order_by(MatchRecordModel.completed_at.desc()).limit(100).all()
    return [
        {
            "match_id": match.match_id,
            "room_code": match.room_code,
            "game_mode": match.game_mode,
            "result": player_match.result,
            "opponents": json.loads(player_match.opponent_names_json),
            "rating_delta": player_match.rating_delta,
            "xp_awarded": player_match.xp_awarded,
            "completed_at": match.completed_at.isoformat(),
            "duration_seconds": match.duration_seconds,
            "rated": match.is_rated,
            "moves": json.loads(match.moves_json),
        }
        for player_match, match in rows
    ]


@router.get("/api/leaderboard")
def leaderboard(
    game_mode: str = "four_player",
    category: str = "rating",
    period: str = "all_time",
    search: Optional[str] = Query(default=None, max_length=24),
    offset: int = Query(default=0, ge=0, le=100_000),
    limit: int = Query(default=50, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    """Rank verified profiles; rows are deterministic and never accept client ratings."""
    valid_modes = {"four_player", "classic", "all"}
    valid_categories = {"rating", "wins", "streak", "xp", "weekly", "monthly"}
    if game_mode not in valid_modes:
        raise HTTPException(status_code=422, detail="Unsupported leaderboard mode")
    if category not in valid_categories:
        raise HTTPException(status_code=422, detail="Unsupported leaderboard category")
    if period not in {"all_time", "weekly", "monthly"}:
        raise HTTPException(status_code=422, detail="Unsupported leaderboard period")
    if category in {"weekly", "monthly"}:
        period = category
    elif period != "all_time":
        category = period
    if category == "rating" and game_mode == "all":
        raise HTTPException(status_code=422, detail="Rating rankings require a specific game mode")
    if search is not None and not search.strip():
        search = None

    current_profile = _authenticated_profile(authorization, db) if authorization else None
    cache_key = (
        game_mode, category, period, search.casefold() if search else None,
        offset, limit, current_profile.id if current_profile else None,
    )
    now = time.monotonic()
    with _leaderboard_cache_lock:
        cached = _leaderboard_cache.get(cache_key)
        if cached and now - cached[0] < LEADERBOARD_CACHE_SECONDS:
            return cached[1]

    cutoff: Optional[datetime] = None
    if period == "weekly":
        current_date = datetime.now(timezone.utc).date()
        cutoff_date = current_date - timedelta(days=current_date.weekday())
        cutoff = datetime.combine(cutoff_date, datetime.min.time(), timezone.utc)
    elif period == "monthly":
        current_date = datetime.now(timezone.utc).date()
        cutoff = datetime(current_date.year, current_date.month, 1, tzinfo=timezone.utc)

    match_query = db.query(
        PlayerMatchModel.profile_id.label("profile_id"),
        func.count(PlayerMatchModel.id).label("games"),
        func.coalesce(func.sum(case((PlayerMatchModel.result == "win", 1), else_=0)), 0).label("wins"),
        func.coalesce(func.sum(PlayerMatchModel.xp_awarded), 0).label("xp"),
        func.coalesce(
            func.sum(case((MatchRecordModel.is_rated.is_(True), 1), else_=0)), 0
        ).label("rated_games"),
        func.coalesce(func.sum(PlayerMatchModel.rating_delta), 0).label("rating_delta"),
    ).join(MatchRecordModel, PlayerMatchModel.match_id == MatchRecordModel.match_id)
    if game_mode != "all":
        match_query = match_query.filter(MatchRecordModel.game_mode == game_mode)
    if cutoff is not None:
        match_query = match_query.filter(MatchRecordModel.completed_at >= cutoff)
    stats = match_query.group_by(PlayerMatchModel.profile_id).subquery()

    rating_column = (
        PlayerProfileModel.classic_rating if game_mode == "classic"
        else PlayerProfileModel.four_player_rating
    )
    games = func.coalesce(stats.c.games, 0)
    wins = func.coalesce(stats.c.wins, 0)
    xp = func.coalesce(stats.c.xp, 0)
    rated_games = func.coalesce(stats.c.rated_games, 0)
    rating_delta = func.coalesce(stats.c.rating_delta, 0)
    tie_wins = wins
    if category == "rating":
        score = rating_column
    elif category == "wins":
        score = wins
    elif category == "streak":
        score = PlayerProfileModel.best_streak
    else:
        score = xp
    ranked_query = db.query(
        PlayerProfileModel.id.label("profile_id"),
        PlayerProfileModel.username.label("username"),
        PlayerProfileModel.username_key.label("username_key"),
        PlayerProfileModel.avatar.label("avatar"),
        rating_column.label("rating"),
        score.label("score"),
        games.label("games"),
        wins.label("wins"),
        xp.label("xp"),
        rating_delta.label("rating_delta"),
        func.round(
            wins * 100.0 / func.nullif(games, 0), 1
        ).label("win_percentage"),
    ).outerjoin(stats, stats.c.profile_id == PlayerProfileModel.id).filter(
        PlayerProfileModel.is_suspended.is_(False),
        PlayerProfileModel.deleted_at.is_(None),
    )
    if category == "rating":
        ranked_query = ranked_query.filter(rated_games > 0)
    if period != "all_time":
        ranked_query = ranked_query.filter(stats.c.profile_id.is_not(None))
    ranked = ranked_query.add_columns(
        func.row_number().over(
            order_by=(score.desc(), tie_wins.desc(), PlayerProfileModel.username_key.asc())
        ).label("rank")
    ).subquery()
    filtered = db.query(ranked)
    if search:
        escaped = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filtered = filtered.filter(ranked.c.username.ilike(f"%{escaped}%", escape="\\"))
    total = filtered.count()
    entries = filtered.order_by(ranked.c.rank).offset(offset).limit(limit).all()
    podium = db.query(ranked).filter(ranked.c.rank <= 3).order_by(ranked.c.rank).all()

    def serialize(row: Any) -> dict[str, Any]:
        values = row._mapping
        games = values["games"] or 0
        wins = values["wins"] or 0
        return {
            "rank": values["rank"],
            "username": values["username"],
            "avatar": values["avatar"],
            "rating": values["rating"],
            "score": values["score"],
            "rating_change": values["rating_delta"] if period != "all_time" else values["rating"] - 1200,
            "games": games,
            "wins": wins,
            "win_percentage": float(values["win_percentage"] or 0),
        }

    current_position = None
    if current_profile:
        current_row = db.query(ranked).filter(ranked.c.profile_id == current_profile.id).first()
        if current_row:
            rank = current_row._mapping["rank"]
            neighbors = db.query(ranked).filter(
                ranked.c.rank.between(max(1, rank - 2), rank + 2)
            ).order_by(ranked.c.rank).all()
            current_position = {
                "rank": rank,
                "player": serialize(current_row),
                "neighbors": [serialize(row) for row in neighbors],
            }
    response = {
        "game_mode": game_mode,
        "category": category,
        "period": period,
        "entries": [serialize(row) for row in entries],
        "podium": [serialize(row) for row in podium],
        "total": total,
        "offset": offset,
        "limit": limit,
        "current_player": current_position,
    }
    with _leaderboard_cache_lock:
        _leaderboard_cache[cache_key] = (time.monotonic(), response)
        if len(_leaderboard_cache) > 256:
            expired = [
                key for key, (cached_at, _) in _leaderboard_cache.items()
                if time.monotonic() - cached_at >= LEADERBOARD_CACHE_SECONDS
            ]
            for key in expired:
                _leaderboard_cache.pop(key, None)
    return response


@router.get("/api/players/{username}")
def public_profile(username: str, db: Session = Depends(get_db)):
    if len(username) > 24:
        raise HTTPException(status_code=404, detail="Player not found")
    profile = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.username_key == username.casefold(),
        PlayerProfileModel.is_suspended.is_(False),
        PlayerProfileModel.deleted_at.is_(None),
    ).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Player not found")
    total, wins = db.query(
        func.count(PlayerMatchModel.id),
        func.coalesce(func.sum(case((PlayerMatchModel.result == "win", 1), else_=0)), 0),
    ).filter(PlayerMatchModel.profile_id == profile.id).one()
    matches = db.query(PlayerMatchModel, MatchRecordModel).join(
        MatchRecordModel, PlayerMatchModel.match_id == MatchRecordModel.match_id
    ).filter(PlayerMatchModel.profile_id == profile.id).order_by(
        MatchRecordModel.completed_at.desc()
    ).limit(10).all()
    return {
        "username": profile.username,
        "avatar": profile.avatar,
        "level": _level_progress(profile.xp)["level"],
        "xp": profile.xp,
        "ratings": {
            "classic": profile.classic_rating,
            "four_player": profile.four_player_rating,
        },
        "games": total,
        "wins": wins,
        "win_percentage": round(wins * 100 / total, 1) if total else 0,
        "best_streak": profile.best_streak,
        "recent_matches": [
            {
                "game_mode": match.game_mode,
                "result": player_match.result,
                "opponents": json.loads(player_match.opponent_names_json),
                "completed_at": match.completed_at.isoformat(),
            }
            for player_match, match in matches
        ],
    }


def classic_comeback(moves: list[dict[str, str]], winner: str) -> bool:
    """A Classic comeback requires a verified 3-point material deficit before winning."""
    if winner not in {"white", "black"}:
        return False
    board = chess.Board()
    largest_deficit = 0
    for record in moves:
        move = chess.Move.from_uci(record["uci"])
        if move not in board.legal_moves:
            return False
        board.push(move)
        white_material = sum(
            PIECE_VALUES[piece.piece_type]
            for piece in board.piece_map().values()
            if piece.color == chess.WHITE
        )
        black_material = sum(
            PIECE_VALUES[piece.piece_type]
            for piece in board.piece_map().values()
            if piece.color == chess.BLACK
        )
        margin = white_material - black_material
        player_margin = margin if winner == "white" else -margin
        largest_deficit = max(largest_deficit, -player_margin)
    return largest_deficit >= 3


def _unlock_achievements(
    db: Session,
    profile: PlayerProfileModel,
    result: str,
    game_mode: str,
    comeback: bool,
):
    total, wins = db.query(
        func.count(PlayerMatchModel.id),
        func.coalesce(func.sum(case((PlayerMatchModel.result == "win", 1), else_=0)), 0),
    ).filter(PlayerMatchModel.profile_id == profile.id).one()
    total += 1
    wins += result == "win"
    keys: set[str] = set()
    if wins >= 1:
        keys.add("first_victory")
    if total >= 10:
        keys.add("ten_games")
    if wins >= 10:
        keys.add("ten_wins")
    if profile.best_streak >= 5:
        keys.add("five_streak")
    if result == "win" and game_mode == "four_player":
        keys.add("four_player_champion")
    if result == "win" and comeback and game_mode == "classic":
        keys.add("comeback")
    if profile.classic_rating >= 2000:
        keys.add("chess_master")
    existing = {
        row.achievement_key
        for row in db.query(ProfileAchievementModel).filter(
            ProfileAchievementModel.profile_id == profile.id
        ).all()
    }
    db.add_all(
        ProfileAchievementModel(profile_id=profile.id, achievement_key=key)
        for key in keys - existing
    )


def record_completed_match(
    db: Session,
    *,
    match_id: str,
    room_code: str,
    game_mode: str,
    started_at: Optional[datetime],
    moves: list[Any],
    participants: list[dict[str, Any]],
    winner_profile_id: Optional[str],
    is_draw: bool,
    duration_seconds: int,
    rated: bool,
    comeback: bool = False,
) -> bool:
    """Persist one authoritative match and award progression once per match."""
    if db.query(MatchRecordModel.id).filter(MatchRecordModel.match_id == match_id).first():
        return False
    profiles = {
        profile.id: profile
        for profile in db.query(PlayerProfileModel).filter(
            PlayerProfileModel.id.in_([
                participant["profile_id"]
                for participant in participants
                if participant.get("profile_id")
            ])
        ).all()
    }
    linked = [
        participant for participant in participants
        if participant.get("profile_id") in profiles
    ]
    is_rated = (
        rated
        and len(linked) >= 2
        and len(linked) == len(participants)
        and len({item["profile_id"] for item in linked}) == len(linked)
    )
    db.add(MatchRecordModel(
        match_id=match_id,
        room_code=room_code,
        game_mode=game_mode,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        duration_seconds=max(0, int(duration_seconds)),
        moves_json=json.dumps(moves),
        is_rated=is_rated,
    ))
    if not linked:
        db.commit()
        _invalidate_leaderboard_cache()
        return True

    original_ratings = {
        profile_id: (
            profiles[profile_id].classic_rating
            if game_mode == "classic"
            else profiles[profile_id].four_player_rating
        )
        for profile_id in profiles
    }
    if is_rated and game_mode == "classic" and len(linked) == 2:
        first, second = linked
        first_id, second_id = first["profile_id"], second["profile_id"]
        first_score = 0.5 if is_draw else (1.0 if first_id == winner_profile_id else 0.0)
        expected_first = 1 / (1 + 10 ** ((original_ratings[second_id] - original_ratings[first_id]) / 400))
        delta_first = round(32 * (first_score - expected_first))
        profiles[first_id].classic_rating += delta_first
        profiles[second_id].classic_rating -= delta_first
    elif is_rated and game_mode == "four_player":
        for participant in linked:
            player_id = participant["profile_id"]
            opponents = [
                original_ratings[other["profile_id"]]
                for other in linked if other["profile_id"] != player_id
            ]
            expected = 1 / (1 + 10 ** (
                (sum(opponents) / len(opponents) - original_ratings[player_id]) / 400
            ))
            actual = 0.5 if is_draw else (1.0 if player_id == winner_profile_id else 0.0)
            profiles[player_id].four_player_rating += round(24 * (actual - expected))

    names = [item["username"] for item in participants]
    for participant in linked:
        profile = profiles[participant["profile_id"]]
        outcome = (
            "draw" if is_draw
            else "win" if participant["profile_id"] == winner_profile_id
            else "loss"
        )
        previous_rating = original_ratings[profile.id]
        current_rating = profile.classic_rating if game_mode == "classic" else profile.four_player_rating
        rating_delta = current_rating - previous_rating if is_rated else 0
        xp_awarded = 25 if outcome == "win" else 10 if outcome == "loss" else 15
        profile.xp += xp_awarded
        profile.current_streak = profile.current_streak + 1 if outcome == "win" else 0
        profile.best_streak = max(profile.best_streak, profile.current_streak)
        db.add(PlayerMatchModel(
            match_id=match_id,
            profile_id=profile.id,
            username=profile.username,
            opponent_names_json=json.dumps([
                name for name in names if name != participant["username"]
            ]),
            result=outcome,
            rating_delta=rating_delta,
            xp_awarded=xp_awarded,
        ))
        _unlock_achievements(
            db, profile, outcome, game_mode,
            comeback and participant["profile_id"] == winner_profile_id,
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if db.query(MatchRecordModel.id).filter(MatchRecordModel.match_id == match_id).first():
            return False
        raise
    _invalidate_leaderboard_cache()
    return True
