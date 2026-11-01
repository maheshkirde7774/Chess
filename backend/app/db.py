"""
SQLite Database Configuration and ORM Models for Neon Four Chess
"""

import os
import datetime
from sqlalchemy import Boolean, create_engine, Column, Integer, String, DateTime, Text, UniqueConstraint, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "neon_four_chess.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH}")

def get_utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class RoomModel(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(10), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)
    status = Column(String(20), default="WAITING")  # WAITING, PLAYING, COMPLETED
    players_json = Column(Text, default="{}")       # {role: {"player_id": id, "name": name, "connected": bool}}
    state_json = Column(Text, default="{}")         # Serialized 4PC engine state
    settings_json = Column(Text, default="{}")
    winner = Column(Integer, nullable=True)
    match_id = Column(String(36), nullable=True, index=True)
    started_at = Column(DateTime, nullable=True)


class GameHistoryModel(Base):
    __tablename__ = "game_history"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(10), index=True, nullable=False)
    winner = Column(Integer, nullable=True)
    total_moves = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)
    completed_at = Column(DateTime, default=get_utc_now)
    moves_history_json = Column(Text, default="[]")
    match_id = Column(String(36), unique=True, nullable=True)


class ClassicRoomModel(Base):
    __tablename__ = "classic_rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(10), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)
    mode = Column(String(10), nullable=False)
    time_control = Column(String(10), nullable=False)
    status = Column(String(20), default="WAITING")
    players_json = Column(Text, default="{}")
    state_json = Column(Text, default="{}")
    is_private = Column(Boolean, default=True, nullable=False)
    ai_config_json = Column(Text, default="{}")
    match_id = Column(String(36), nullable=True, index=True)
    started_at = Column(DateTime, nullable=True)


class PlayerProfileModel(Base):
    __tablename__ = "player_profiles"

    id = Column(String(36), primary_key=True)
    username = Column(String(24), nullable=False)
    username_key = Column(String(24), unique=True, index=True, nullable=False)
    avatar = Column(String(16), nullable=False, default="knight")
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    xp = Column(Integer, default=0, nullable=False)
    classic_rating = Column(Integer, default=1200, nullable=False)
    four_player_rating = Column(Integer, default=1200, nullable=False)
    current_streak = Column(Integer, default=0, nullable=False)
    best_streak = Column(Integer, default=0, nullable=False)


class MatchRecordModel(Base):
    __tablename__ = "match_records"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String(36), unique=True, index=True, nullable=False)
    room_code = Column(String(10), nullable=False)
    game_mode = Column(String(20), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, default=get_utc_now, nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)
    moves_json = Column(Text, default="[]", nullable=False)
    is_rated = Column(Boolean, default=False, nullable=False)


class PlayerMatchModel(Base):
    __tablename__ = "player_matches"
    __table_args__ = (
        UniqueConstraint("match_id", "profile_id", name="uq_player_match_profile"),
    )

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(String(36), index=True, nullable=False)
    profile_id = Column(String(36), index=True, nullable=False)
    username = Column(String(24), nullable=False)
    opponent_names_json = Column(Text, default="[]", nullable=False)
    result = Column(String(10), nullable=False)
    rating_delta = Column(Integer, default=0, nullable=False)
    xp_awarded = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


class ProfileAchievementModel(Base):
    __tablename__ = "profile_achievements"
    __table_args__ = (
        UniqueConstraint("profile_id", "achievement_key", name="uq_profile_achievement"),
    )

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(String(36), index=True, nullable=False)
    achievement_key = Column(String(40), nullable=False)
    unlocked_at = Column(DateTime, default=get_utc_now, nullable=False)


def init_db():
    """Initializes tables in database."""
    Base.metadata.create_all(bind=engine)
    if "settings_json" not in {column["name"] for column in inspect(engine).get_columns("rooms")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE rooms ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'"))
    if "is_private" not in {column["name"] for column in inspect(engine).get_columns("classic_rooms")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE classic_rooms ADD COLUMN is_private BOOLEAN NOT NULL DEFAULT TRUE"))
    if "ai_config_json" not in {column["name"] for column in inspect(engine).get_columns("classic_rooms")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE classic_rooms ADD COLUMN ai_config_json TEXT NOT NULL DEFAULT '{}'"))
    for table_name in ("rooms", "classic_rooms"):
        columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
        for column_name, column_type in (
            ("match_id", "VARCHAR(36)"),
            ("started_at", "DATETIME"),
        ):
            if column_name not in columns:
                with engine.begin() as connection:
                    connection.execute(text(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    ))
    if "match_id" not in {column["name"] for column in inspect(engine).get_columns("game_history")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE game_history ADD COLUMN match_id VARCHAR(36)"))
    if "is_rated" not in {column["name"] for column in inspect(engine).get_columns("match_records")}:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE match_records ADD COLUMN is_rated BOOLEAN NOT NULL DEFAULT FALSE"
            ))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
