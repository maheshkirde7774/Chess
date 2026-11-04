"""Device-scoped player profiles, progression, ratings, and verified match history."""

import hashlib
import json
import re
import secrets
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Optional
from urllib.error import URLError
from urllib.request import Request as URLRequest, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import chess
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import (
    DailyPuzzleModel,
    MatchRecordModel,
    PlayerDailyPuzzleModel,
    PlayerMatchModel,
    PlayerProfileModel,
    PlayerPuzzleAttemptModel,
    PlayerPuzzleProgressModel,
    ProfileAchievementModel,
    get_db,
)
from app.room_limits import enforce_room_rate_limit

router = APIRouter()
_leaderboard_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_leaderboard_cache_lock = threading.Lock()
LEADERBOARD_CACHE_SECONDS = 30

AVATAR_UNLOCK_XP = {
    "king": 0,
    "queen": 0,
    "rook": 0,
    "bishop": 0,
    "knight": 0,
    "pawn": 0,
    "dragon": 200,
    "phoenix": 400,
    "cyber_cat": 600,
    "royal_lion": 800,
}
AVATARS = set(AVATAR_UNLOCK_XP)
BOARD_THEME_UNLOCK_XP = {
    "classic_wood": 0,
    "marble": 0,
    "midnight": 100,
    "ocean": 150,
    "emerald": 300,
    "royal_gold": 500,
    "neon_cyber": 800,
    "minimal_light": 0,
}
PIECE_SET_UNLOCK_XP = {
    "staunton": 0,
    "modern": 0,
    "minimal": 100,
    "royal": 300,
    "futuristic": 600,
}
PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}


class SoundEventPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    move: bool = True
    capture: bool = True
    check: bool = True
    checkmate: bool = True
    start: bool = True
    completion: bool = True
    notification: bool = True
    ui: bool = True


class SoundPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    volume: float = Field(default=0.65, ge=0, le=1)
    events: SoundEventPreferences = Field(default_factory=SoundEventPreferences)


class AnimationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    movement: bool = True
    board_transition: bool = True
    move_highlighting: bool = True
    celebrations: bool = True
    reduced_motion: bool = False


class CustomizationPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    board_theme: Literal[
        "classic_wood", "marble", "midnight", "ocean",
        "emerald", "royal_gold", "neon_cyber", "minimal_light",
    ] = "classic_wood"
    piece_set: Literal["staunton", "modern", "minimal", "royal", "futuristic"] = "staunton"
    sound: SoundPreferences = Field(default_factory=SoundPreferences)
    animations: AnimationPreferences = Field(default_factory=AnimationPreferences)


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Optional[str] = Field(default=None, min_length=3, max_length=20)
    avatar: Optional[str] = Field(default=None, max_length=16)
    timezone: Optional[str] = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            _timezone_for(value)
        return value


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: Optional[str] = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            _timezone_for(value)
        return value


class PuzzleMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    puzzle_id: str = Field(min_length=3, max_length=32)
    move: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")


class PuzzleReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    puzzle_id: str = Field(min_length=3, max_length=32)


class PracticePuzzleMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    move: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
    moves: list[str] = Field(default_factory=list, max_length=80)


def _timezone_for(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("Timezone must be a valid IANA timezone") from error


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
        "timezone": profile.timezone,
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
    create: ProfileCreate,
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
        timezone=create.timezone,
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
    if update.username is None and update.avatar is None and update.timezone is None:
        raise HTTPException(status_code=422, detail="Provide a username, avatar, or timezone to update")
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
        required_xp = AVATAR_UNLOCK_XP[update.avatar]
        if profile.xp < required_xp:
            raise HTTPException(
                status_code=403,
                detail=f"That avatar requires {required_xp} XP to unlock",
            )
        profile.avatar = update.avatar
    if update.timezone is not None and update.timezone != (profile.timezone or "UTC"):
        if db.query(PlayerPuzzleAttemptModel.id).filter(
            PlayerPuzzleAttemptModel.profile_id == profile.id
        ).first():
            raise HTTPException(
                status_code=409,
                detail="Timezone cannot change after a daily puzzle attempt has started",
            )
        profile.timezone = update.timezone
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username is already taken")
    db.refresh(profile)
    _invalidate_leaderboard_cache()
    return _profile_payload(db, profile)


@router.get("/api/profile/customization")
def get_customization(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    stored = json.loads(profile.customization_json or "{}")
    return {
        **CustomizationPreferences.model_validate(stored).model_dump(),
        "configured": bool(stored),
    }


@router.put("/api/profile/customization")
def update_customization(
    preferences: CustomizationPreferences,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    required_theme_xp = BOARD_THEME_UNLOCK_XP[preferences.board_theme]
    required_piece_xp = PIECE_SET_UNLOCK_XP[preferences.piece_set]
    if profile.xp < required_theme_xp:
        raise HTTPException(
            status_code=403,
            detail=f"This board theme requires {required_theme_xp} XP to unlock",
        )
    if profile.xp < required_piece_xp:
        raise HTTPException(
            status_code=403,
            detail=f"This piece set requires {required_piece_xp} XP to unlock",
        )
    profile.customization_json = json.dumps(
        preferences.model_dump(), sort_keys=True, separators=(",", ":")
    )
    db.commit()
    db.refresh(profile)
    return {
        **CustomizationPreferences.model_validate(
            json.loads(profile.customization_json)
        ).model_dump(),
        "configured": True,
    }


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


def _fetch_lichess_daily() -> dict[str, Any]:
    request = URLRequest(
        "https://lichess.org/api/puzzle/daily",
        headers={"Accept": "application/json", "User-Agent": "FOURX-Daily-Puzzles/1.0"},
    )
    try:
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=503,
            detail="Daily puzzle source is temporarily unavailable; please retry",
        ) from error
    if not isinstance(data, dict):
        raise HTTPException(status_code=502, detail="Puzzle source returned invalid data")
    return data


def _puzzle_difficulty(rating: int) -> str:
    if rating < 1200:
        return "easy"
    if rating < 1600:
        return "medium"
    if rating < 2000:
        return "hard"
    return "expert"


def _puzzle_objective(themes: list[str]) -> str:
    mate_theme = next((theme for theme in themes if re.fullmatch(r"mateIn[1-9]", theme)), None)
    if mate_theme:
        return f"Find the forced checkmate in {mate_theme[6:]}."
    if "crushing" in themes:
        return "Find the forcing continuation that wins decisive material."
    return "Find the strongest forcing continuation."


def _load_daily_puzzle(db: Session, utc_date: str) -> DailyPuzzleModel:
    saved = db.query(DailyPuzzleModel).filter(
        DailyPuzzleModel.source_date == utc_date
    ).first()
    if saved:
        return saved

    data = _fetch_lichess_daily()
    puzzle_data = data.get("puzzle")
    game_data = data.get("game")
    if not isinstance(puzzle_data, dict) or not isinstance(game_data, dict):
        raise HTTPException(status_code=502, detail="Puzzle source returned an incomplete puzzle")
    puzzle_id = puzzle_data.get("id")
    fen = puzzle_data.get("fen")
    solution = puzzle_data.get("solution")
    rating = puzzle_data.get("rating")
    game_id = game_data.get("id")
    pgn = game_data.get("pgn")
    themes = puzzle_data.get("themes", [])
    if (
        not isinstance(puzzle_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", puzzle_id)
        or not isinstance(fen, str)
        or not isinstance(solution, list)
        or not solution
        or len(solution) > 80
        or not isinstance(rating, int)
        or not isinstance(game_id, str)
        or not isinstance(pgn, str)
        or not isinstance(themes, list)
        or any(not isinstance(theme, str) for theme in themes)
    ):
        raise HTTPException(status_code=502, detail="Puzzle source returned invalid fields")
    try:
        board = chess.Board(fen)
    except ValueError as error:
        raise HTTPException(status_code=502, detail="Puzzle source returned an invalid position") from error
    if not board.is_valid():
        raise HTTPException(status_code=502, detail="Puzzle source returned an invalid position")
    normalized_solution: list[str] = []
    for uci in solution:
        if not isinstance(uci, str):
            raise HTTPException(status_code=502, detail="Puzzle source returned an invalid solution")
        try:
            move = chess.Move.from_uci(uci)
        except ValueError as error:
            raise HTTPException(status_code=502, detail="Puzzle source returned an invalid solution") from error
        if move not in board.legal_moves:
            raise HTTPException(status_code=502, detail="Puzzle source returned an illegal solution")
        normalized_solution.append(move.uci())
        board.push(move)

    saved = DailyPuzzleModel(
        puzzle_id=puzzle_id,
        source_date=utc_date,
        rating=rating,
        fen=fen,
        solution_json=json.dumps([normalized_solution]),
        themes_json=json.dumps(themes),
        game_id=game_id,
        pgn=pgn,
    )
    db.add(saved)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        saved = db.query(DailyPuzzleModel).filter(
            DailyPuzzleModel.source_date == utc_date
        ).first()
        if saved is None:
            raise HTTPException(status_code=503, detail="Daily puzzle could not be saved; please retry")
    return saved


def _daily_assignment(
    db: Session,
    profile: PlayerProfileModel,
) -> tuple[PlayerDailyPuzzleModel, DailyPuzzleModel, str]:
    now = datetime.now(timezone.utc)
    local_date = _local_puzzle_date(profile, now)
    assignment = db.query(PlayerDailyPuzzleModel).filter(
        PlayerDailyPuzzleModel.profile_id == profile.id,
        PlayerDailyPuzzleModel.local_date == local_date,
    ).first()
    if assignment is not None:
        puzzle = db.query(DailyPuzzleModel).filter(
            DailyPuzzleModel.puzzle_id == assignment.puzzle_id
        ).first()
        if puzzle is None:
            raise HTTPException(status_code=500, detail="Assigned daily puzzle is unavailable")
        return assignment, puzzle, local_date

    puzzle = _load_daily_puzzle(db, now.date().isoformat())
    already_attempted = db.query(PlayerPuzzleAttemptModel.id).filter(
        PlayerPuzzleAttemptModel.profile_id == profile.id,
        PlayerPuzzleAttemptModel.puzzle_id == puzzle.puzzle_id,
    ).first()
    if already_attempted:
        attempted_puzzles = {
            row[0] for row in db.query(PlayerPuzzleAttemptModel.puzzle_id).filter(
                PlayerPuzzleAttemptModel.profile_id == profile.id,
            ).all()
        }
        puzzle = db.query(DailyPuzzleModel).filter(
            DailyPuzzleModel.puzzle_id.notin_(attempted_puzzles | {puzzle.puzzle_id}),
        ).order_by(DailyPuzzleModel.source_date.desc()).first()
        if puzzle is None:
            raise HTTPException(
                status_code=503,
                detail="A new daily puzzle is not available yet in your timezone",
            )
    assignment = PlayerDailyPuzzleModel(
        profile_id=profile.id,
        local_date=local_date,
        puzzle_id=puzzle.puzzle_id,
    )
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        assignment = db.query(PlayerDailyPuzzleModel).filter(
            PlayerDailyPuzzleModel.profile_id == profile.id,
            PlayerDailyPuzzleModel.local_date == local_date,
        ).first()
        if assignment is None:
            raise HTTPException(status_code=409, detail="Daily puzzle assignment changed; reload and retry")
        puzzle = db.query(DailyPuzzleModel).filter(
            DailyPuzzleModel.puzzle_id == assignment.puzzle_id
        ).first()
        if puzzle is None:
            raise HTTPException(status_code=500, detail="Assigned daily puzzle is unavailable")
        return assignment, puzzle, local_date
    return assignment, puzzle, local_date


def _local_puzzle_date(profile: PlayerProfileModel, now: datetime) -> str:
    return now.astimezone(_timezone_for(profile.timezone or "UTC")).date().isoformat()


def _next_puzzle_streak(
    current: int,
    best: int,
    last_completed: Optional[str],
    local_date: str,
) -> tuple[int, int]:
    today = date.fromisoformat(local_date)
    last_date = date.fromisoformat(last_completed) if last_completed else None
    next_current = current + 1 if last_date == today - timedelta(days=1) else 1
    return next_current, max(best, next_current)


def _puzzle_progress(db: Session, profile_id: str) -> dict[str, int]:
    progress = db.query(PlayerPuzzleProgressModel).filter(
        PlayerPuzzleProgressModel.profile_id == profile_id
    ).first()
    if progress is None:
        return {
            "current_streak": 0,
            "best_streak": 0,
            "total_attempted": 0,
            "total_completed": 0,
            "first_attempt_correct": 0,
            "accuracy": 0,
            "total_xp_earned": 0,
        }
    return {
        "current_streak": progress.current_streak,
        "best_streak": progress.best_streak,
        "total_attempted": progress.total_attempted,
        "total_completed": progress.total_completed,
        "first_attempt_correct": progress.first_attempt_correct,
        "accuracy": round(
            progress.first_attempt_correct * 100 / progress.total_attempted,
            1,
        ) if progress.total_attempted else 0,
        "total_xp_earned": progress.total_xp_earned,
    }


def _attempt_payload(attempt: Optional[PlayerPuzzleAttemptModel]) -> dict[str, Any]:
    if attempt is None:
        return {
            "moves": [],
            "incorrect_attempts": 0,
            "hint_count": 0,
            "completed": False,
            "first_attempt_correct": False,
            "xp_awarded": 0,
        }
    return {
        "moves": json.loads(attempt.moves_json),
        "incorrect_attempts": attempt.incorrect_attempts,
        "hint_count": attempt.hint_count,
        "completed": attempt.completed,
        "first_attempt_correct": attempt.first_attempt_correct,
        "xp_awarded": attempt.xp_awarded,
    }


def _puzzle_explanation(puzzle: DailyPuzzleModel) -> str:
    line = json.loads(puzzle.solution_json)[0]
    board = chess.Board(puzzle.fen)
    notation = []
    for uci in line:
        move = chess.Move.from_uci(uci)
        notation.append(board.san(move))
        board.push(move)
    return (
        f"The verified solution is {', '.join(notation)}. "
        "This is the best continuation from the position in the source game."
    )


def _public_puzzle_payload(
    puzzle: DailyPuzzleModel,
    *,
    local_date: Optional[str] = None,
    attempt: Optional[PlayerPuzzleAttemptModel] = None,
) -> dict[str, Any]:
    themes = json.loads(puzzle.themes_json)
    result = {
        "puzzle_id": puzzle.puzzle_id,
        "published_date": puzzle.source_date,
        "challenge_date": local_date or puzzle.source_date,
        "fen": puzzle.fen,
        "rating": puzzle.rating,
        "difficulty": _puzzle_difficulty(puzzle.rating),
        "objective": _puzzle_objective(themes),
        "themes": themes,
        "source": "Lichess Daily Puzzle",
        "source_url": f"https://lichess.org/training/{puzzle.puzzle_id}",
        "attempt": _attempt_payload(attempt),
    }
    if attempt and attempt.completed:
        result["explanation"] = _puzzle_explanation(puzzle)
    return result


def _get_or_create_daily_attempt(
    db: Session,
    profile_id: str,
    puzzle_id: str,
    local_date: str,
) -> PlayerPuzzleAttemptModel:
    attempt = db.query(PlayerPuzzleAttemptModel).filter(
        PlayerPuzzleAttemptModel.profile_id == profile_id,
        PlayerPuzzleAttemptModel.local_date == local_date,
    ).first()
    if attempt:
        if attempt.puzzle_id != puzzle_id:
            raise HTTPException(status_code=409, detail="Today's daily puzzle has already been started")
        if attempt.completed:
            raise HTTPException(status_code=409, detail="Today's daily puzzle is already complete")
        return attempt
    previously_attempted = db.query(PlayerPuzzleAttemptModel.id).filter(
        PlayerPuzzleAttemptModel.profile_id == profile_id,
        PlayerPuzzleAttemptModel.puzzle_id == puzzle_id,
    ).first()
    if previously_attempted:
        raise HTTPException(status_code=409, detail="This puzzle has already been attempted")
    attempt = PlayerPuzzleAttemptModel(
        profile_id=profile_id,
        puzzle_id=puzzle_id,
        local_date=local_date,
        moves_json="[]",
    )
    progress = db.query(PlayerPuzzleProgressModel).filter(
        PlayerPuzzleProgressModel.profile_id == profile_id
    ).first()
    if progress is None:
        progress = PlayerPuzzleProgressModel(
            profile_id=profile_id,
            current_streak=0,
            best_streak=0,
            total_attempted=0,
            total_completed=0,
            first_attempt_correct=0,
            total_xp_earned=0,
        )
        db.add(progress)
    progress.total_attempted += 1
    db.add(attempt)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.query(PlayerPuzzleAttemptModel).filter(
            PlayerPuzzleAttemptModel.profile_id == profile_id,
            PlayerPuzzleAttemptModel.local_date == local_date,
        ).first()
        if existing is None or existing.puzzle_id != puzzle_id:
            raise HTTPException(status_code=409, detail="A daily puzzle attempt already exists")
        if existing.completed:
            raise HTTPException(status_code=409, detail="Today's daily puzzle is already complete")
        return existing
    return attempt


def _advance_puzzle_line(
    puzzle: DailyPuzzleModel,
    accepted_moves: list[str],
    submitted_move: str,
) -> dict[str, Any]:
    board = chess.Board(puzzle.fen)
    solutions: list[list[str]] = json.loads(puzzle.solution_json)
    for uci in accepted_moves:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise HTTPException(status_code=500, detail="Stored puzzle progress is invalid")
        board.push(move)
    branches = [
        line for line in solutions
        if len(line) > len(accepted_moves) and line[:len(accepted_moves)] == accepted_moves
    ]
    if not branches:
        raise HTTPException(status_code=422, detail="Previous moves do not match a valid solution line")
    try:
        move = chess.Move.from_uci(submitted_move)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Move must be a valid UCI chess move") from error
    if move not in board.legal_moves:
        raise HTTPException(status_code=422, detail="That move is illegal in this position")
    matching = [line for line in branches if line[len(accepted_moves)] == move.uci()]
    if not matching:
        return {"correct": False}

    line = matching[0]
    new_moves = [*accepted_moves, move.uci()]
    san_moves = [board.san(move)]
    board.push(move)
    opponent_move = None
    if len(new_moves) < len(line):
        reply = chess.Move.from_uci(line[len(new_moves)])
        if reply not in board.legal_moves:
            raise HTTPException(status_code=500, detail="Stored puzzle reply is illegal")
        opponent_move = reply.uci()
        san_moves.append(board.san(reply))
        new_moves.append(opponent_move)
        board.push(reply)
    completed = len(new_moves) >= len(line)
    explanation = _puzzle_explanation(puzzle) if completed else None
    return {
        "correct": True,
        "moves": new_moves,
        "opponent_move": opponent_move,
        "completed": completed,
        "san": san_moves,
        "explanation": explanation,
    }


def _puzzle_hint(puzzle: DailyPuzzleModel, accepted_moves: list[str], hint_level: int) -> str:
    solutions: list[list[str]] = json.loads(puzzle.solution_json)
    if not any(
        line[:len(accepted_moves)] == accepted_moves
        and len(line) > len(accepted_moves)
        for line in solutions
    ):
        raise HTTPException(status_code=422, detail="Previous moves do not match a valid solution line")
    line = next(
        (candidate for candidate in solutions
         if candidate[:len(accepted_moves)] == accepted_moves
         and len(candidate) > len(accepted_moves)),
        None,
    )
    if line is None:
        return "Look for forcing checks, captures, and threats."
    board = chess.Board(puzzle.fen)
    for uci in accepted_moves:
        board.push_uci(uci)
    move = chess.Move.from_uci(line[len(accepted_moves)])
    piece = board.piece_at(move.from_square)
    if hint_level <= 1:
        piece_name = chess.piece_name(piece.piece_type) if piece else "piece"
        return f"Look for a forcing move with your {piece_name}."
    return f"Find the move from {chess.square_name(move.from_square)} to {chess.square_name(move.to_square)}."


@router.get("/api/puzzles/daily")
def get_daily_puzzle(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    assignment, puzzle, local_date = _daily_assignment(db, profile)
    attempt = db.query(PlayerPuzzleAttemptModel).filter(
        PlayerPuzzleAttemptModel.profile_id == profile.id,
        PlayerPuzzleAttemptModel.local_date == local_date,
    ).first()
    return {
        **_public_puzzle_payload(puzzle, local_date=local_date, attempt=attempt),
        "progress": _puzzle_progress(db, profile.id),
    }


@router.post("/api/puzzles/daily/move")
def submit_daily_puzzle_move(
    move_request: PuzzleMove,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    enforce_room_rate_limit(request, f"puzzle-move:{profile.id}", limit=120)
    assignment, puzzle, local_date = _daily_assignment(db, profile)
    if move_request.puzzle_id != assignment.puzzle_id:
        raise HTTPException(status_code=409, detail="This is not today's assigned puzzle")
    attempt = _get_or_create_daily_attempt(db, profile.id, puzzle.puzzle_id, local_date)
    previous_moves = json.loads(attempt.moves_json)
    result = _advance_puzzle_line(puzzle, previous_moves, move_request.move)
    if not result["correct"]:
        attempt.incorrect_attempts += 1
        db.commit()
        return {
            "correct": False,
            "incorrect_attempts": attempt.incorrect_attempts,
            "message": "That is a legal move, but it does not solve the puzzle.",
        }
    attempt.moves_json = json.dumps(result["moves"])
    if not result["completed"]:
        db.commit()
        return {
            **result,
            "incorrect_attempts": attempt.incorrect_attempts,
            "progress": _puzzle_progress(db, profile.id),
        }

    base_xp = {"easy": 10, "medium": 15, "hard": 20, "expert": 25}[
        _puzzle_difficulty(puzzle.rating)
    ]
    first_attempt = attempt.incorrect_attempts == 0
    reward = base_xp + (5 if first_attempt else 0)
    completed_at = datetime.now(timezone.utc)
    completion_update = db.query(PlayerPuzzleAttemptModel).filter(
        PlayerPuzzleAttemptModel.id == attempt.id,
        PlayerPuzzleAttemptModel.completed.is_(False),
    ).update(
        {
            PlayerPuzzleAttemptModel.completed: True,
            PlayerPuzzleAttemptModel.first_attempt_correct: first_attempt,
            PlayerPuzzleAttemptModel.xp_awarded: reward,
            PlayerPuzzleAttemptModel.completed_at: completed_at,
            PlayerPuzzleAttemptModel.moves_json: json.dumps(result["moves"]),
        },
        synchronize_session=False,
    )
    if completion_update != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Daily puzzle completion was already recorded")
    progress = db.query(PlayerPuzzleProgressModel).filter(
        PlayerPuzzleProgressModel.profile_id == profile.id
    ).one()
    progress.current_streak, progress.best_streak = _next_puzzle_streak(
        progress.current_streak,
        progress.best_streak,
        progress.last_completed_date,
        local_date,
    )
    progress.total_completed += 1
    progress.first_attempt_correct += int(first_attempt)
    progress.total_xp_earned += reward
    progress.last_completed_date = local_date
    profile.xp += reward
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Daily puzzle reward was already recorded") from error
    _invalidate_leaderboard_cache()
    return {
        **result,
        "first_attempt_correct": first_attempt,
        "xp_awarded": reward,
        "total_xp": profile.xp,
        "progress": _puzzle_progress(db, profile.id),
    }


@router.post("/api/puzzles/daily/hint")
def daily_puzzle_hint(
    hint_request: PuzzleReset,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    enforce_room_rate_limit(request, f"puzzle-hint:{profile.id}", limit=30)
    assignment, puzzle, local_date = _daily_assignment(db, profile)
    if hint_request.puzzle_id != assignment.puzzle_id:
        raise HTTPException(status_code=409, detail="This is not today's assigned puzzle")
    attempt = _get_or_create_daily_attempt(db, profile.id, puzzle.puzzle_id, local_date)
    attempt.hint_count += 1
    db.commit()
    return {
        "hint": _puzzle_hint(
            puzzle,
            json.loads(attempt.moves_json),
            min(attempt.hint_count, 2),
        ),
        "hint_count": attempt.hint_count,
    }


@router.post("/api/puzzles/daily/reset")
def reset_daily_puzzle(
    reset_request: PuzzleReset,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    enforce_room_rate_limit(request, f"puzzle-reset:{profile.id}", limit=30)
    assignment, _puzzle, local_date = _daily_assignment(db, profile)
    if reset_request.puzzle_id != assignment.puzzle_id:
        raise HTTPException(status_code=409, detail="This is not today's assigned puzzle")
    attempt = db.query(PlayerPuzzleAttemptModel).filter(
        PlayerPuzzleAttemptModel.profile_id == profile.id,
        PlayerPuzzleAttemptModel.local_date == local_date,
    ).first()
    if attempt and attempt.completed:
        raise HTTPException(status_code=409, detail="A completed daily puzzle cannot be reset")
    if attempt:
        attempt.moves_json = "[]"
        db.commit()
    return {"moves": [], "message": "Puzzle position reset; your attempt and hint history remain saved."}


@router.get("/api/puzzles/archive")
def puzzle_archive(
    difficulty: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0, le=100_000),
    limit: int = Query(default=25, ge=1, le=100),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    if difficulty not in (None, "easy", "medium", "hard", "expert"):
        raise HTTPException(status_code=422, detail="Unsupported puzzle difficulty")
    _daily_assignment(db, profile)
    query = db.query(DailyPuzzleModel).order_by(
        DailyPuzzleModel.source_date.desc(), DailyPuzzleModel.puzzle_id.asc()
    )
    if difficulty:
        rating_ranges = {
            "easy": (0, 1199),
            "medium": (1200, 1599),
            "hard": (1600, 1999),
            "expert": (2000, 100000),
        }
        lower, upper = rating_ranges[difficulty]
        query = query.filter(DailyPuzzleModel.rating.between(lower, upper))
    total = query.count()
    puzzles = query.offset(offset).limit(limit).all()
    attempts = {
        row.puzzle_id: row
        for row in db.query(PlayerPuzzleAttemptModel).filter(
            PlayerPuzzleAttemptModel.profile_id == profile.id,
            PlayerPuzzleAttemptModel.puzzle_id.in_(
                [puzzle.puzzle_id for puzzle in puzzles] or [""]
            ),
        ).all()
    }
    return {
        "entries": [
            {
                **_public_puzzle_payload(puzzle),
                "completed": bool(attempts.get(puzzle.puzzle_id) and attempts[puzzle.puzzle_id].completed),
                "xp_awarded": attempts[puzzle.puzzle_id].xp_awarded if puzzle.puzzle_id in attempts else 0,
            }
            for puzzle in puzzles
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/api/puzzles/archive/{puzzle_id}")
def get_archived_puzzle(
    puzzle_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    puzzle = db.query(DailyPuzzleModel).filter(DailyPuzzleModel.puzzle_id == puzzle_id).first()
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Archived puzzle not found")
    attempt = db.query(PlayerPuzzleAttemptModel).filter(
        PlayerPuzzleAttemptModel.profile_id == profile.id,
        PlayerPuzzleAttemptModel.puzzle_id == puzzle_id,
        PlayerPuzzleAttemptModel.completed.is_(True),
    ).first()
    return {
        **_public_puzzle_payload(puzzle, attempt=attempt),
        "practice_only": True,
    }


@router.post("/api/puzzles/archive/{puzzle_id}/move")
def submit_archive_puzzle_move(
    puzzle_id: str,
    move_request: PracticePuzzleMove,
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    enforce_room_rate_limit(request, f"puzzle-practice:{profile.id}", limit=120)
    puzzle = db.query(DailyPuzzleModel).filter(DailyPuzzleModel.puzzle_id == puzzle_id).first()
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Archived puzzle not found")
    if any(not isinstance(move, str) or not re.fullmatch(
        r"[a-h][1-8][a-h][1-8][qrbn]?", move
    ) for move in move_request.moves):
        raise HTTPException(status_code=422, detail="Previous moves contain invalid UCI notation")
    result = _advance_puzzle_line(puzzle, move_request.moves, move_request.move)
    return {**result, "practice_only": True}


@router.get("/api/puzzles/archive/{puzzle_id}/hint")
def archived_puzzle_hint(
    puzzle_id: str,
    request: Request,
    hint_level: int = Query(default=1, ge=1, le=2),
    moves: list[str] = Query(default=[]),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authenticated_profile(authorization, db)
    enforce_room_rate_limit(request, f"puzzle-practice-hint:{profile.id}", limit=30)
    puzzle = db.query(DailyPuzzleModel).filter(DailyPuzzleModel.puzzle_id == puzzle_id).first()
    if puzzle is None:
        raise HTTPException(status_code=404, detail="Archived puzzle not found")
    if any(not re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", move) for move in moves):
        raise HTTPException(status_code=422, detail="Previous moves contain invalid UCI notation")
    return {
        "hint": _puzzle_hint(puzzle, moves, hint_level),
        "practice_only": True,
    }


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
    puzzle_xp_query = db.query(
        PlayerPuzzleAttemptModel.profile_id.label("profile_id"),
        func.coalesce(func.sum(PlayerPuzzleAttemptModel.xp_awarded), 0).label("xp"),
    ).filter(
        PlayerPuzzleAttemptModel.completed.is_(True),
    )
    if cutoff is not None:
        puzzle_xp_query = puzzle_xp_query.filter(PlayerPuzzleAttemptModel.completed_at >= cutoff)
    if game_mode == "four_player":
        puzzle_xp_query = puzzle_xp_query.filter(False)
    puzzle_xp_stats = puzzle_xp_query.group_by(
        PlayerPuzzleAttemptModel.profile_id
    ).subquery()

    rating_column = (
        PlayerProfileModel.classic_rating if game_mode == "classic"
        else PlayerProfileModel.four_player_rating
    )
    games = func.coalesce(stats.c.games, 0)
    wins = func.coalesce(stats.c.wins, 0)
    xp = func.coalesce(stats.c.xp, 0)
    puzzle_xp = func.coalesce(puzzle_xp_stats.c.xp, 0)
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
        score = (
            PlayerProfileModel.xp
            if period == "all_time"
            else xp + (0 if game_mode == "four_player" else puzzle_xp)
        )
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
    ).outerjoin(stats, stats.c.profile_id == PlayerProfileModel.id).outerjoin(
        puzzle_xp_stats,
        puzzle_xp_stats.c.profile_id == PlayerProfileModel.id,
    ).filter(
        PlayerProfileModel.is_suspended.is_(False),
        PlayerProfileModel.deleted_at.is_(None),
    )
    if category == "rating":
        ranked_query = ranked_query.filter(rated_games > 0)
    if period != "all_time":
        ranked_query = ranked_query.filter(
            or_(
                stats.c.profile_id.is_not(None),
                puzzle_xp_stats.c.profile_id.is_not(None),
            )
        )
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
