"""
SQLite Database Configuration and ORM Models for Neon Four Chess
"""

import os
import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
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
    winner = Column(Integer, nullable=True)


class GameHistoryModel(Base):
    __tablename__ = "game_history"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(10), index=True, nullable=False)
    winner = Column(Integer, nullable=True)
    total_moves = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)
    completed_at = Column(DateTime, default=get_utc_now)
    moves_history_json = Column(Text, default="[]")


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


def init_db():
    """Initializes tables in database."""
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
