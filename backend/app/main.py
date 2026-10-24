"""
Neon Four Chess - FastAPI Backend
Provides REST endpoints, SQLite persistence, and WebSockets for real-time multiplayer 4-player chess.
"""

import os
import json
import uuid
import random
import string
import logging
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import init_db, get_db, RoomModel, GameHistoryModel
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

def generate_room_code(length: int = 6) -> str:
    """Generates a random uppercase room code (e.g. NEON42)."""
    chars = string.ascii_uppercase + string.digits
    # Avoid easily confused letters
    chars = chars.replace('O', '').replace('0', '').replace('I', '').replace('1', '')
    return "".join(random.choices(chars, k=length))

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
            # We can reconstruct or initialize
            pass
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

    room_runtime = {
        "engine": engine,
        "players": players_data,
        "status": room_record.status or "WAITING"
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
    room_record.winner = room_data["engine"].winner
    db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    logger.info("Initializing SQLite database...")
    init_db()
    yield
    logger.info("Shutting down Neon Four Chess server...")

app = FastAPI(
    title="Neon Four Chess API",
    description="Backend API and WebSockets for 4-Player Neon Chess",
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

# ----------------- REST ENDPOINTS -----------------

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "Neon Four Chess",
        "active_rooms": len(active_rooms)
    }

@app.post("/rooms", response_model=CreateRoomResponse)
def create_room(req: CreateRoomRequest, db: Session = Depends(get_db)):
    """Creates a new game room and assigns Player 1 (Cyan) to the creator."""
    room_code = generate_room_code()
    while db.query(RoomModel).filter(RoomModel.room_code == room_code).first():
        room_code = generate_room_code()

    player_id = str(uuid.uuid4())
    player_role = PLAYER_CYAN
    player_name = req.player_name.strip() or "Player 1"

    engine = FourPlayerChessEngine()
    players = {
        player_role: {
            "player_id": player_id,
            "name": player_name,
            "connected": False
        }
    }

    active_rooms[room_code] = {
        "engine": engine,
        "players": players,
        "status": "WAITING"
    }

    # Save to SQLite
    room_record = RoomModel(
        room_code=room_code,
        status="WAITING",
        players_json=json.dumps(players),
        state_json=json.dumps(engine.get_state())
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
async def join_room(req: JoinRoomRequest, db: Session = Depends(get_db)):
    """Joins an existing room and assigns the next open player role (1..4)."""
    room_code = req.room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)

    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    players = room_data["players"]

    # Find first vacant role from 1 to 4
    assigned_role = None
    for role in [PLAYER_CYAN, PLAYER_MAGENTA, PLAYER_LIME, PLAYER_GOLD]:
        if role not in players:
            assigned_role = role
            break

    if assigned_role is None:
        raise HTTPException(status_code=400, detail="Room is full (all 4 seats are occupied)")

    player_id = str(uuid.uuid4())
    player_name = req.player_name.strip() or f"Player {assigned_role}"

    players[assigned_role] = {
        "player_id": player_id,
        "name": player_name,
        "connected": False
    }

    # If 4 players have joined, update status to PLAYING
    if len(players) == 4 and room_data["status"] == "WAITING":
        room_data["status"] = "PLAYING"

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
        winner=engine.winner
    )

@app.post("/rooms/{room_code}/move")
async def execute_move(room_code: str, req: MoveRequest, db: Session = Depends(get_db)):
    """Server-authoritative move endpoint."""
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    engine: FourPlayerChessEngine = room_data["engine"]

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
async def reset_room(room_code: str, db: Session = Depends(get_db)):
    """Resets the board for a new match in the same room."""
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)
    if not room_data:
        raise HTTPException(status_code=404, detail="Room not found")

    room_data["engine"] = FourPlayerChessEngine()
    room_data["status"] = "PLAYING" if len(room_data["players"]) == 4 else "WAITING"
    persist_room_state(db, room_code)

    await manager.broadcast_to_room(room_code, {
        "type": "GAME_RESET",
        "room_code": room_code,
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
    player_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    room_code = room_code.strip().upper()
    room_data = get_or_create_room_runtime(db, room_code)

    if not room_data:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # If player_id not provided in query, client must send auth frame first
    current_player_id = player_id
    role = _get_role_by_player_id(room_data["players"], current_player_id) if current_player_id else None

    # Connect to room manager
    client_key = current_player_id or str(uuid.uuid4())
    await manager.connect(room_code, client_key, websocket)

    # Send initial state snapshot to client
    await manager.send_personal_message(room_code, client_key, {
        "type": "SYNC_STATE",
        "room_code": room_code,
        "your_role": role,
        "status": room_data["status"],
        "players": _sanitize_players(room_data["players"]),
        "game_state": room_data["engine"].get_state()
    })

    if role is not None:
        room_data["players"][role]["connected"] = True
        persist_room_state(db, room_code)
        await manager.broadcast_to_room(room_code, {
            "type": "PRESENCE_UPDATE",
            "role": role,
            "connected": True,
            "players": _sanitize_players(room_data["players"])
        })

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue

            msg_type = payload.get("type")

            if msg_type == "PING":
                await manager.send_personal_message(room_code, client_key, {"type": "PONG"})

            elif msg_type == "AUTH":
                # Late authentication
                auth_id = payload.get("player_id")
                if auth_id:
                    matched_role = _get_role_by_player_id(room_data["players"], auth_id)
                    if matched_role:
                        current_player_id = auth_id
                        role = matched_role
                        room_data["players"][role]["connected"] = True
                        persist_room_state(db, room_code)
                        await manager.broadcast_to_room(room_code, {
                            "type": "PRESENCE_UPDATE",
                            "role": role,
                            "connected": True,
                            "players": _sanitize_players(room_data["players"])
                        })

            elif msg_type == "MOVE":
                engine: FourPlayerChessEngine = room_data["engine"]
                # Verify authorization
                if role is None or role != engine.current_turn:
                    await manager.send_personal_message(room_code, client_key, {
                        "type": "ERROR",
                        "message": "Not your turn or unauthorized"
                    })
                    continue

                from_sq = payload.get("from")
                to_sq = payload.get("to")
                promotion = payload.get("promotion")

                if not from_sq or not to_sq:
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
                if role is not None and role in engine.active_players:
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

            elif msg_type == "CHAT":
                # Neon chat message
                text = str(payload.get("text", "")).strip()[:100]
                if text:
                    sender_name = room_data["players"].get(role, {}).get("name", "Spectator") if role else "Spectator"
                    await manager.broadcast_to_room(room_code, {
                        "type": "CHAT",
                        "sender": sender_name,
                        "role": role,
                        "text": text
                    })

    except WebSocketDisconnect:
        manager.disconnect(room_code, client_key)
        if role is not None and role in room_data["players"]:
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
            "connected": info.get("connected", False)
        }
    return sanitized

def _get_role_by_player_id(players: Dict[int, Dict[str, Any]], player_id: Optional[str]) -> Optional[int]:
    if not player_id:
        return None
    for role, info in players.items():
        if info.get("player_id") == player_id:
            return role
    return None

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
        return {"message": "Neon Four Chess Backend API is Running"}
