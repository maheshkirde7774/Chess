"""
SQLite Database Configuration and ORM Models for Neon Four Chess
"""

import os
import datetime
from sqlalchemy import Boolean, create_engine, Column, Integer, String, DateTime, Text, UniqueConstraint, Index, inspect, text
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
    spectator_token = Column(String(64), nullable=True)
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
    is_suspended = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    timezone = Column(String(64), nullable=True)


class MatchRecordModel(Base):
    __tablename__ = "match_records"
    __table_args__ = (
        Index("ix_match_mode_completed", "game_mode", "completed_at"),
        Index("ix_match_mode_rated", "game_mode", "is_rated"),
    )

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


class DailyPuzzleModel(Base):
    __tablename__ = "daily_puzzles"

    puzzle_id = Column(String(32), primary_key=True)
    source_date = Column(String(10), unique=True, index=True, nullable=False)
    rating = Column(Integer, nullable=False)
    fen = Column(Text, nullable=False)
    solution_json = Column(Text, nullable=False)
    themes_json = Column(Text, nullable=False, default="[]")
    game_id = Column(String(32), nullable=False)
    pgn = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


class PlayerDailyPuzzleModel(Base):
    __tablename__ = "player_daily_puzzles"
    __table_args__ = (
        UniqueConstraint("profile_id", "local_date", name="uq_profile_daily_puzzle_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(String(36), index=True, nullable=False)
    local_date = Column(String(10), nullable=False)
    puzzle_id = Column(String(32), index=True, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


class PlayerPuzzleAttemptModel(Base):
    __tablename__ = "player_puzzle_attempts"
    __table_args__ = (
        UniqueConstraint("profile_id", "local_date", name="uq_puzzle_attempt_profile_date"),
        UniqueConstraint("profile_id", "puzzle_id", name="uq_puzzle_attempt_profile_puzzle"),
    )

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(String(36), index=True, nullable=False)
    puzzle_id = Column(String(32), nullable=False)
    local_date = Column(String(10), nullable=False)
    moves_json = Column(Text, nullable=False, default="[]")
    incorrect_attempts = Column(Integer, default=0, nullable=False)
    hint_count = Column(Integer, default=0, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    first_attempt_correct = Column(Boolean, default=False, nullable=False)
    xp_awarded = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime, default=get_utc_now, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class PlayerPuzzleProgressModel(Base):
    __tablename__ = "player_puzzle_progress"

    profile_id = Column(String(36), primary_key=True)
    current_streak = Column(Integer, default=0, nullable=False)
    best_streak = Column(Integer, default=0, nullable=False)
    total_attempted = Column(Integer, default=0, nullable=False)
    total_completed = Column(Integer, default=0, nullable=False)
    first_attempt_correct = Column(Integer, default=0, nullable=False)
    total_xp_earned = Column(Integer, default=0, nullable=False)
    last_completed_date = Column(String(10), nullable=True)


class ProfileAchievementModel(Base):
    __tablename__ = "profile_achievements"
    __table_args__ = (
        UniqueConstraint("profile_id", "achievement_key", name="uq_profile_achievement"),
    )

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(String(36), index=True, nullable=False)
    achievement_key = Column(String(40), nullable=False)
    unlocked_at = Column(DateTime, default=get_utc_now, nullable=False)


class FriendRequestModel(Base):
    __tablename__ = "friend_requests"
    __table_args__ = (
        UniqueConstraint("pair_key", name="uq_friend_request_pair"),
        Index("ix_friend_request_recipient_status", "addressee_id", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(String(36), nullable=False, index=True)
    addressee_id = Column(String(36), nullable=False, index=True)
    pair_key = Column(String(73), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    updated_at = Column(DateTime, default=get_utc_now, nullable=False)


class FriendshipModel(Base):
    __tablename__ = "friendships"
    __table_args__ = (
        UniqueConstraint("pair_key", name="uq_friendship_pair"),
        Index("ix_friendship_low_player", "player_low_id"),
        Index("ix_friendship_high_player", "player_high_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    player_low_id = Column(String(36), nullable=False)
    player_high_id = Column(String(36), nullable=False)
    pair_key = Column(String(73), nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


class BlockedPlayerModel(Base):
    __tablename__ = "blocked_players"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_blocked_player_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(String(36), nullable=False, index=True)
    blocked_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


class ConversationModel(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("pair_key", name="uq_conversation_pair"),
        Index("ix_conversation_participant_a", "participant_a_id"),
        Index("ix_conversation_participant_b", "participant_b_id"),
    )

    id = Column(String(36), primary_key=True)
    participant_a_id = Column(String(36), nullable=False)
    participant_b_id = Column(String(36), nullable=False)
    pair_key = Column(String(73), nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


class PrivateMessageModel(Base):
    __tablename__ = "private_messages"
    __table_args__ = (
        Index("ix_private_message_conversation_created", "conversation_id", "created_at"),
        Index("ix_private_message_recipient_read", "recipient_id", "read_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(36), nullable=False)
    sender_id = Column(String(36), nullable=False, index=True)
    recipient_id = Column(String(36), nullable=False, index=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)


class SocialNotificationModel(Base):
    __tablename__ = "social_notifications"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_social_notification_dedupe"),
        Index("ix_social_notification_recipient_created", "recipient_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(String(36), nullable=False, index=True)
    actor_id = Column(String(36), nullable=True)
    notification_type = Column(String(32), nullable=False)
    dedupe_key = Column(String(180), nullable=False)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    read_at = Column(DateTime, nullable=True)


class GameInvitationModel(Base):
    __tablename__ = "game_invitations"
    __table_args__ = (
        Index("ix_game_invitation_recipient_status", "recipient_id", "status"),
        Index("ix_game_invitation_sender_status", "sender_id", "status"),
        Index("uq_game_invitation_active_key", "active_key", unique=True),
    )

    id = Column(String(36), primary_key=True)
    sender_id = Column(String(36), nullable=False, index=True)
    recipient_id = Column(String(36), nullable=False, index=True)
    game_mode = Column(String(20), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    active_key = Column(String(100), nullable=True)
    room_code = Column(String(10), nullable=True)
    sender_player_id = Column(String(100), nullable=True)
    recipient_player_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=get_utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class PlayerReportModel(Base):
    __tablename__ = "player_reports"
    __table_args__ = (
        Index("ix_player_report_reported_created", "reported_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(String(36), nullable=False, index=True)
    reported_id = Column(String(36), nullable=False, index=True)
    category = Column(String(24), nullable=False)
    details = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=get_utc_now, nullable=False)


def init_db():
    """Initializes tables in database."""
    Base.metadata.create_all(bind=engine)
    if "settings_json" not in {column["name"] for column in inspect(engine).get_columns("rooms")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE rooms ADD COLUMN settings_json TEXT NOT NULL DEFAULT '{}'"))
    if "is_private" not in {column["name"] for column in inspect(engine).get_columns("classic_rooms")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE classic_rooms ADD COLUMN is_private BOOLEAN NOT NULL DEFAULT TRUE"))
    if "spectator_token" not in {column["name"] for column in inspect(engine).get_columns("classic_rooms")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE classic_rooms ADD COLUMN spectator_token VARCHAR(64)"))
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
    profile_columns = {column["name"] for column in inspect(engine).get_columns("player_profiles")}
    if "is_suspended" not in profile_columns:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE player_profiles ADD COLUMN is_suspended BOOLEAN NOT NULL DEFAULT FALSE"
            ))
    if "deleted_at" not in profile_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE player_profiles ADD COLUMN deleted_at DATETIME"))
    if "timezone" not in profile_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE player_profiles ADD COLUMN timezone VARCHAR(64)"))
    invitation_columns = {column["name"] for column in inspect(engine).get_columns("game_invitations")}
    if "active_key" not in invitation_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE game_invitations ADD COLUMN active_key VARCHAR(100)"))
    for index in MatchRecordModel.__table__.indexes:
        index.create(bind=engine, checkfirst=True)
    for index in GameInvitationModel.__table__.indexes:
        index.create(bind=engine, checkfirst=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
