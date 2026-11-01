"""
FOURX FastAPI backend
Provides REST endpoints, SQLite persistence, and WebSockets for multiplayer chess.
"""

import os
import asyncio
import json
import secrets
import string
import logging
import re
import time
from collections import deque
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import init_db, get_db, RoomModel, GameHistoryModel, ClassicRoomModel
from app.engine import (
    FourPlayerChessEngine, Move,
    PLAYER_CYAN, PLAYER_MAGENTA, PLAYER_LIME, PLAYER_GOLD,
    PLAYER_NAMES, PLAYER_COLORS
)
from app.models import (
    CreateRoomRequest, CreateRoomResponse,
    JoinRoomRequest, JoinRoomResponse,
    MoveRequest, ResignRequest, RoomStateResponse
)
from app.ws_manager import manager
from app.classic import router as classic_router
from app.room_limits import enforce_room_rate_limit as _rate_limit

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("neon_four_chess")

# In-memory runtime state for active rooms
# room_code -> {
#    "engine": FourPlayerChessEngine,
#    "players": {
#        role (int 1..4): {
#            "player_id": str,
#            "name": str,
#            "connected": bool
#        }
#    },
#    "status": str ("WAITING", "PLAYING", "COMPLETED")
# }
active_rooms: Dict[str, Dict[str, Any]] = {}
ROOM_CODE_CHARS = string.ascii_uppercase.replace("O", "").replace("I", "") + "23456789"
SUPPORTED_TIME_CONTROLS = {"unlimited", "5+0", "10+0", "15+10"}

def generate_room_code(length: int = 6) -> str:
    """Generates a random uppercase room code (e.g. NEON42)."""
    return "".join(secrets.choice(ROOM_CODE_CHARS) for _ in range(length))

def _new_player_id() -> str:
    return secrets.token_urlsafe(32)

def _settings(room_data: Dict[str, Any]) -> Dict[str, Any]:
    return room_data.get("settings", {
        "game_mode": "four_player",
        "is_private": True,
        "time_control": "unlimited",
        "max_players": 4,
    })

def get_or_create_room_runtime(db: Session, room_code: str) -> Optional[Dict[str, Any]]:
    """Loads room from memory or SQLite database."""
    if room_code in active_rooms:
        return active_rooms[room_code]

    # Try loading from database
    room_record = db.query(RoomModel).filter(RoomModel.room_code == room_code).first()
    if not room_record:
        return None

    engine = FourPlayerChessEngine()
    if room_record.state_json and room_record.state_json != "{}":
        try:
            saved_state = json.loads(room_record.state_json)
            engine.load_state(saved_state)
        except Exception as e:
            logger.error(f"Error restoring state for {room_code}: {e}")

    players_data = {}
    if room_record.players_json:
        try:
            raw_players = json.loads(room_record.players_json)
            # keys might be strings in json
            players_data = {int(k): v for k, v in raw_players.items()}
        except Exception:
            players_data = {}
    try:
        settings = json.loads(room_record.settings_json or "{}")
    except (TypeError, json.JSONDecodeError):
        settings = {}

    room_runtime = {
        "engine": engine,
        "players": players_data,
        "status": room_record.status or "WAITING",
        "settings": {
            "game_mode": "four_player",
            "is_private": True,
            "time_control": "unlimited",
            "max_players": 4,
            **settings,
        },
    }
    active_rooms[room_code] = room_runtime
    return room_runtime

def persist_room_state(db: Session, room_code: str):
    """Persists current room runtime state into SQLite."""
    if room_code not in active_rooms:
        return

    room_data = active_rooms[room_code]
    room_record = db.query(RoomModel).filter(RoomModel.room_code == room_code).first()
    if not room_record:
        room_record = RoomModel(room_code=room_code)
        db.add(room_record)

    room_record.status = room_data["status"]
    room_record.players_json = json.dumps(room_data["players"])
    room_record.state_json = json.dumps(room_data["engine"].get_state())
    room_record.settings_json = json.dumps(_settings(room_data))
    room_record.winner = room_data["engine"].winner
    db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    logger.info("Initializing SQLite database...")
    init_db()
    yield
    logger.info("Shutting down FOURX server...")

app = FastAPI(
    title="FOURX API",
    description="Backend API and WebSockets for FOURX chess",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for web frontend & mobile apps (Capacitor)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(classic_router)

# ----------------- REST ENDPOINTS -----------------

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "FOURX",
        "active_rooms": len(active_rooms)
    }

@app.post("/rooms", response_model=CreateRoomResponse)
def create_room(req: CreateRoomRequest, request: Request, db: Session = Depends(get_db)):
    """Creates a new game room and assigns Player 1 (Cyan) to the creator."""
    _rate_limit(request, "create")
    if req.time_control not in SUPPORTED_TIME_CONTROLS:
        raise HTTPException(status_code=422, detail="Unsupported time control")
    room_code = generate_room_code()
    while (
        db.query(RoomModel).filter(RoomModel.room_code == room_code).first()
        or db.query(ClassicRoomModel).filter(ClassicRoomModel.room_code == room_code).first()
    ):
        room_code = generate_room_code()

    player_id = _new_player_id()
    player_role = PLAYER_CYAN
    player_name = req.player_name.strip() or "Player 1"

    engine = FourPlayerChessEngine()
    players = {
        player_role: {
            "player_id": player_id,
            "name": player_name,
            "connected": False,
            "ready": True,
            "host": True,
        }
    }

    active_rooms[room_code] = {
        "engine": engine,
        "players": players,
        "status": "WAITING",
        "settings": {
            "game_mode": "four_player",
            "is_private": req.is_private,
            "time_control": req.time_control,
            "max_players": 4,
        },
    }

    # Save to SQLite
    room_record = RoomModel(
        room_code=room_code,
        status="WAITING",
        players_json=json.dumps(players),
        state_json=json.dumps(engine.get_state()),
        settings_json=json.dumps(active_rooms[room_code]["settings"]),
    )
    db.add(room_record)
    db.commit()

    logger.info(f"Room {room_code} created by {player_name} (Role: {player_role})")
    return CreateRoomResponse(
        room_code=room_code,
        player_id=player_id,
        player_role=player_role,
        player_name=player_name,
        message="Room created successfully"
    )

@app.post("/rooms/join", response_model=JoinRoomResponse)
async def join_room(req: JoinRoomRequest, request: Request, db: Session = Depends(get_db)):
    """Joins an existing room and assigns the next open player role (1..4)."""
    _rate_limit(request, "join", limit=20)
    room_code = req.room_code.strip().upper()
    if not re.fullmatch(r"[A-HJ-NP-Z2-9]{6}", room_code):
        raise HTTPException(status_code=422, detail="Invalid room code format")
    room_data = get_or_create_room_runtime(db, room_code)

    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    if room_data["status"] != "WAITING":
        raise HTTPException(status_code=400, detail="Room is not accepting players")

    players = room_data["players"]

    # Find first vacant role from 1 to 4
    assigned_role = None
    for role in [PLAYER_CYAN, PLAYER_MAGENTA, PLAYER_LIME, PLAYER_GOLD]:
        if role not in players:
            assigned_role = role
            break

    if assigned_role is None:
        raise HTTPException(status_code=400, detail="Room is full (all 4 seats are occupied)")

    player_id = _new_player_id()
    player_name = req.player_name.strip() or f"Player {assigned_role}"

    players[assigned_role] = {
        "player_id": player_id,
        "name": player_name,
        "connected": False,
        "ready": False,
        "host": False,
    }

    persist_room_state(db, room_code)

    # Broadcast event to other players
    await manager.broadcast_to_room(room_code, {
        "type": "PLAYER_JOINED",
        "room_code": room_code,
        "role": assigned_role,
        "name": player_name,
        "status": room_data["status"],
        "players": _sanitize_players(players)
    })

    logger.info(f"Player {player_name} joined room {room_code} as Role {assigned_role}")
    return JoinRoomResponse(
        room_code=room_code,
        player_id=player_id,
        player_role=assigned_role,
        player_name=player_name,
        message=f"Joined room as {PLAYER_NAMES[assigned_role]}"
    )

@app.get("/rooms/{room_code}", response_model=RoomStateResponse)
def get_room_state(room_code: str, db: Session = Depends(get_db)):
    """Returns current sanitized room state, players, and game board."""
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)

    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    engine = room_data["engine"]
    state = engine.get_state()

    return RoomStateResponse(
        room_code=room_code,
        status=room_data["status"],
        current_turn=engine.current_turn,
        active_players=engine.active_players,
        players=_sanitize_players(room_data["players"]),
        game_state=state,
        winner=engine.winner,
        settings=_settings(room_data),
        host_role=next((role for role, player in room_data["players"].items() if player.get("host")), None),
    )

@app.get("/rooms")
def list_public_rooms(db: Session = Depends(get_db)):
    """Lists discoverable waiting rooms without exposing player credentials."""
    records = db.query(RoomModel).filter(RoomModel.status == "WAITING").all()
    rooms = []
    for record in records:
        room_data = get_or_create_room_runtime(db, record.room_code)
        if room_data and not _settings(room_data)["is_private"]:
            rooms.append({
                "room_code": record.room_code,
                "status": room_data["status"],
                "players": _sanitize_players(room_data["players"]),
                "settings": _settings(room_data),
                "host_role": next(
                    (role for role, player in room_data["players"].items() if player.get("host")),
                    None,
                ),
            })
    classic_records = db.query(ClassicRoomModel).filter(
        ClassicRoomModel.status == "WAITING",
        ClassicRoomModel.is_private.is_(False),
    ).all()
    for record in classic_records:
        try:
            raw_players = json.loads(record.players_json or "{}")
        except json.JSONDecodeError:
            logger.exception("Could not decode players for classic room %s", record.room_code)
            continue
        rooms.append({
            "room_code": record.room_code,
            "status": record.status,
            "players": {
                side: {
                    "side": side,
                    "name": player.get("name", side.title()),
                    "connected": player.get("connected", False),
                    "ready": player.get("ready", False),
                    "host": player.get("host", False),
                }
                for side, player in raw_players.items()
            },
            "settings": {
                "game_mode": "classic",
                "is_private": False,
                "time_control": record.time_control,
                "max_players": 2,
            },
            "host_role": "white",
        })
    return rooms

@app.post("/rooms/{room_code}/start")
async def start_room(room_code: str, req: ResignRequest, db: Session = Depends(get_db)):
    """Starts a full four-player room when requested by its host."""
    code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, code)
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    role = _get_role_by_player_id(room_data["players"], req.player_id)
    if role is None or not room_data["players"][role].get("host"):
        raise HTTPException(status_code=403, detail="Only the room host can start the game")
    if room_data["status"] != "WAITING":
        raise HTTPException(status_code=400, detail="The game has already started")
    if len(room_data["players"]) != room_data["settings"]["max_players"]:
        raise HTTPException(status_code=400, detail="All player seats must be filled before starting")
    room_data["status"] = "PLAYING"
    persist_room_state(db, code)
    await manager.broadcast_to_room(code, {
        "type": "GAME_STARTED", "room_code": code,
        "players": _sanitize_players(room_data["players"]),
        "game_state": room_data["engine"].get_state(),
    })
    return {"success": True, "status": "PLAYING"}

@app.post("/rooms/{room_code}/leave")
async def leave_room(room_code: str, req: ResignRequest, db: Session = Depends(get_db)):
    """Leaves a waiting room and transfers host to the next occupied seat."""
    code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, code)
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    role = _get_role_by_player_id(room_data["players"], req.player_id)
    if role is None:
        raise HTTPException(status_code=403, detail="Unauthorized: invalid player ID")
    if room_data["status"] != "WAITING":
        raise HTTPException(status_code=400, detail="Started games must be resigned rather than left")
    del room_data["players"][role]
    record = db.query(RoomModel).filter(RoomModel.room_code == code).first()
    if not room_data["players"]:
        db.delete(record)
        db.commit()
        active_rooms.pop(code, None)
    else:
        if not any(player.get("host") for player in room_data["players"].values()):
            new_host = min(room_data["players"])
            room_data["players"][new_host]["host"] = True
        persist_room_state(db, code)
        await manager.broadcast_to_room(code, {
            "type": "PLAYER_LEFT", "role": role,
            "players": _sanitize_players(room_data["players"]),
        })
    await manager.close_player_connection(code, req.player_id)
    return {"success": True}

@app.post("/rooms/{room_code}/move")
async def execute_move(room_code: str, req: MoveRequest, db: Session = Depends(get_db)):
    """Server-authoritative move endpoint."""
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    engine: FourPlayerChessEngine = room_data["engine"]
    if room_data["status"] != "PLAYING":
        raise HTTPException(status_code=400, detail="The host has not started this game")

    # Verify authorization
    player_role = _get_role_by_player_id(room_data["players"], req.player_id)
    if player_role is None:
        raise HTTPException(status_code=403, detail="Unauthorized: invalid player ID")

    if player_role != engine.current_turn:
        raise HTTPException(
            status_code=403,
            detail=f"Not your turn. Current turn: Player {engine.current_turn}"
        )

    # Execute move in engine
    move = Move(tuple(req.from_sq), tuple(req.to_sq), req.promotion)
    success, msg = engine.make_move(move)

    if not success:
        raise HTTPException(status_code=400, detail=msg)

    # Check if game is over
    if engine.is_game_over:
        room_data["status"] = "COMPLETED"
        _record_completed_game(db, room_code, engine)

    persist_room_state(db, room_code)

    # Broadcast move to all connected players via WebSocket
    new_state = engine.get_state()
    await manager.broadcast_to_room(room_code, {
        "type": "MOVE_MADE",
        "room_code": room_code,
        "player": player_role,
        "move": move.to_dict(),
        "game_state": new_state,
        "is_game_over": engine.is_game_over,
        "winner": engine.winner
    })

    return {"success": True, "message": msg, "state": new_state}

@app.post("/rooms/{room_code}/resign")
async def resign_game(room_code: str, req: ResignRequest, db: Session = Depends(get_db)):
    """Allows a player to resign."""
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    engine: FourPlayerChessEngine = room_data["engine"]
    if room_data["status"] != "PLAYING":
        raise HTTPException(status_code=400, detail="The host has not started this game")
    player_role = _get_role_by_player_id(room_data["players"], req.player_id)
    if player_role is None:
        raise HTTPException(status_code=403, detail="Unauthorized: invalid player ID")

    success, msg = engine.resign_player(player_role)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    if engine.is_game_over:
        room_data["status"] = "COMPLETED"
        _record_completed_game(db, room_code, engine)

    persist_room_state(db, room_code)

    await manager.broadcast_to_room(room_code, {
        "type": "PLAYER_RESIGNED",
        "room_code": room_code,
        "player": player_role,
        "game_state": engine.get_state(),
        "is_game_over": engine.is_game_over,
        "winner": engine.winner
    })

    return {"success": True, "message": msg}

@app.post("/rooms/{room_code}/reset")
async def reset_room(room_code: str, req: ResignRequest, db: Session = Depends(get_db)):
    """Resets the board for a new match in the same room."""
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")
    role = _get_role_by_player_id(room_data["players"], req.player_id)
    if role is None or not room_data["players"][role].get("host"):
        raise HTTPException(status_code=403, detail="Only the room host can reset the game")

    room_data["engine"] = FourPlayerChessEngine()
    room_data["status"] = "WAITING"
    persist_room_state(db, room_code)

    await manager.broadcast_to_room(room_code, {
        "type": "GAME_RESET",
        "room_code": room_code,
        "status": room_data["status"],
        "players": _sanitize_players(room_data["players"]),
        "game_state": room_data["engine"].get_state()
    })

    return {"success": True, "message": "Room reset successfully"}

@app.get("/api/history")
def get_game_history(db: Session = Depends(get_db)):
    """Returns list of completed games."""
    records = db.query(GameHistoryModel).order_by(GameHistoryModel.completed_at.desc()).limit(20).all()
    history = []
    for r in records:
        history.append({
            "id": r.id,
            "room_code": r.room_code,
            "winner": r.winner,
            "winner_name": PLAYER_NAMES.get(r.winner, "Draw / None"),
            "total_moves": r.total_moves,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None
        })
    return history

# ----------------- WEBSOCKET ROUTE -----------------

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    db: Session = Depends(get_db)
):
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)

    if not room_data:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        auth_message = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(auth_message) > 4096:
            raise ValueError("Authentication message is too large")
        auth_payload = json.loads(auth_message)
    except (asyncio.TimeoutError, json.JSONDecodeError, ValueError, WebSocketDisconnect):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    player_id = auth_payload.get("player_id") if isinstance(auth_payload, dict) and auth_payload.get("type") == "AUTH" else None
    role = _get_role_by_player_id(room_data["players"], player_id)
    if role is None or not isinstance(player_id, str):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Connect to room manager
    client_key = player_id
    await manager.connect(room_code, client_key, websocket, accepted=True)

    # Send initial state snapshot to client
    await manager.send_personal_message(room_code, client_key, {
        "type": "SYNC_STATE",
        "room_code": room_code,
        "your_role": role,
        "status": room_data["status"],
        "players": _sanitize_players(room_data["players"]),
        "game_state": room_data["engine"].get_state(),
        "settings": _settings(room_data),
        "host_role": next((seat for seat, player in room_data["players"].items() if player.get("host")), None),
    })

    room_data["players"][role]["connected"] = True
    persist_room_state(db, room_code)
    await manager.broadcast_to_room(room_code, {
        "type": "PRESENCE_UPDATE",
        "role": role,
        "connected": True,
        "players": _sanitize_players(room_data["players"])
    })

    try:
        message_times: deque[float] = deque()
        while True:
            data = await websocket.receive_text()
            if len(data) > 4096:
                await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "Message is too large"})
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "Invalid message format"})
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("type"), str):
                await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "Message must be a JSON object with a type"})
                continue
            now = time.monotonic()
            while message_times and now - message_times[0] > 10:
                message_times.popleft()
            if len(message_times) >= 60:
                await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "Message rate limit exceeded"})
                continue
            message_times.append(now)
            msg_type = payload.get("type")

            if msg_type == "PING":
                await manager.send_personal_message(room_code, client_key, {"type": "PONG"})

            elif msg_type == "MOVE":
                engine: FourPlayerChessEngine = room_data["engine"]
                # Verify authorization
                if role is None or role != engine.current_turn:
                    await manager.send_personal_message(room_code, client_key, {
                        "type": "ERROR",
                        "message": "Not your turn or unauthorized"
                    })
                    continue

                if room_data["status"] != "PLAYING":
                    await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "The host has not started this game"})
                    continue
                from_sq = payload.get("from")
                to_sq = payload.get("to")
                promotion = payload.get("promotion")

                if not _valid_square(from_sq) or not _valid_square(to_sq) or (
                    promotion is not None and (not isinstance(promotion, str) or promotion.lower() not in {"q", "r", "b", "n"})
                ):
                    await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "Invalid move format"})
                    continue

                move = Move(tuple(from_sq), tuple(to_sq), promotion)
                success, msg = engine.make_move(move)

                if not success:
                    await manager.send_personal_message(room_code, client_key, {
                        "type": "ERROR",
                        "message": msg
                    })
                else:
                    if engine.is_game_over:
                        room_data["status"] = "COMPLETED"
                        _record_completed_game(db, room_code, engine)

                    persist_room_state(db, room_code)

                    await manager.broadcast_to_room(room_code, {
                        "type": "MOVE_MADE",
                        "room_code": room_code,
                        "player": role,
                        "move": move.to_dict(),
                        "game_state": engine.get_state(),
                        "is_game_over": engine.is_game_over,
                        "winner": engine.winner
                    })

            elif msg_type == "RESIGN":
                engine: FourPlayerChessEngine = room_data["engine"]
                if room_data["status"] == "PLAYING" and role in engine.active_players:
                    success, msg = engine.resign_player(role)
                    if success:
                        if engine.is_game_over:
                            room_data["status"] = "COMPLETED"
                            _record_completed_game(db, room_code, engine)
                        persist_room_state(db, room_code)

                        await manager.broadcast_to_room(room_code, {
                            "type": "PLAYER_RESIGNED",
                            "room_code": room_code,
                            "player": role,
                            "game_state": engine.get_state(),
                            "is_game_over": engine.is_game_over,
                            "winner": engine.winner
                        })
            elif msg_type == "READY":
                room_data["players"][role]["ready"] = payload.get("ready") is True
                persist_room_state(db, room_code)
                await manager.broadcast_to_room(room_code, {
                    "type": "PRESENCE_UPDATE",
                    "players": _sanitize_players(room_data["players"]),
                })
            elif msg_type == "START_GAME":
                if not room_data["players"][role].get("host"):
                    await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "Only the room host can start the game"})
                    continue
                if room_data["status"] != "WAITING":
                    await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "The game has already started"})
                    continue
                if len(room_data["players"]) != room_data["settings"]["max_players"]:
                    await manager.send_personal_message(room_code, client_key, {"type": "ERROR", "message": "All player seats must be filled before starting"})
                    continue
                room_data["status"] = "PLAYING"
                persist_room_state(db, room_code)
                await manager.broadcast_to_room(room_code, {
                    "type": "GAME_STARTED", "room_code": room_code,
                    "players": _sanitize_players(room_data["players"]),
                    "game_state": room_data["engine"].get_state(),
                })

            elif msg_type == "CHAT":
                # Room chat message
                text = str(payload.get("text", "")).strip()[:100]
                if text:
                    sender_name = room_data["players"].get(role, {}).get("name", "Spectator") if role else "Spectator"
                    await manager.broadcast_to_room(room_code, {
                        "type": "CHAT",
                        "sender": sender_name,
                        "role": role,
                        "text": text
                    })
            else:
                await manager.send_personal_message(room_code, client_key, {
                    "type": "ERROR", "message": "Unsupported action",
                })

    except WebSocketDisconnect:
        manager.disconnect(room_code, client_key, websocket)
        if manager.is_player_connected(room_code, client_key):
            return
        if role in room_data["players"]:
            room_data["players"][role]["connected"] = False
            persist_room_state(db, room_code)
            await manager.broadcast_to_room(room_code, {
                "type": "PRESENCE_UPDATE",
                "role": role,
                "connected": False,
                "players": _sanitize_players(room_data["players"])
            })

# ----------------- HELPER FUNCTIONS -----------------

def _sanitize_players(players: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """Sanitizes player objects removing private secret player_ids for client broadcast."""
    sanitized = {}
    for role, info in players.items():
        sanitized[str(role)] = {
            "role": role,
            "name": info.get("name", f"Player {role}"),
            "color": PLAYER_COLORS.get(role, "#ffffff"),
            "connected": info.get("connected", False),
            "ready": info.get("ready", False),
            "host": info.get("host", False),
        }
    return sanitized

def _get_role_by_player_id(players: Dict[int, Dict[str, Any]], player_id: Optional[str]) -> Optional[int]:
    if not player_id:
        return None
    for role, info in players.items():
        if info.get("player_id") == player_id:
            return role
    return None

def _valid_square(square: Any) -> bool:
    return (
        isinstance(square, list)
        and len(square) == 2
        and all(isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 14 for value in square)
    )

def _record_completed_game(db: Session, room_code: str, engine: FourPlayerChessEngine):
    """Saves a completed game to GameHistoryModel."""
    try:
        history_entry = GameHistoryModel(
            room_code=room_code,
            winner=engine.winner,
            total_moves=len(engine.move_history),
            moves_history_json=json.dumps(engine.move_history)
        )
        db.add(history_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to record game history for {room_code}: {e}")

# ----------------- STATIC FRONTEND SERVING -----------------

# Mount frontend directories so all CSS, JS, and asset paths resolve cleanly
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))
if os.path.exists(FRONTEND_DIR):
    css_dir = os.path.join(FRONTEND_DIR, "css")
    js_dir = os.path.join(FRONTEND_DIR, "js")
    assets_dir = os.path.join(FRONTEND_DIR, "assets")

    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    def serve_index():
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "FOURX backend API is running"}
