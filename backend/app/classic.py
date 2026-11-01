"""Classic two-player chess rooms, kept separate from the four-player game."""

import asyncio
import json
import logging
import secrets
import string
import time
import uuid
from typing import Any, Dict, Optional

import chess
from fastapi import APIRouter, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import ClassicRoomModel, get_db
from app.ws_manager import manager
from app.room_limits import enforce_room_rate_limit

logger = logging.getLogger("classic_chess")
router = APIRouter()

TIME_CONTROLS = {
    "1+0": (60, 0),
    "3+0": (180, 0),
    "5+0": (300, 0),
    "10+0": (600, 0),
    "15+10": (900, 10),
    "unlimited": (None, 0),
}
ROOM_CODE_LENGTH = 6
ROOM_CODE_CHARS = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"
classic_rooms: Dict[str, Dict[str, Any]] = {}


class CreateClassicRoomRequest(BaseModel):
    player_name: str = Field(default="White", min_length=1, max_length=30)
    time_control: str = "10+0"
    mode: str = "online"
    is_private: bool = True


class JoinClassicRoomRequest(BaseModel):
    room_code: str = Field(..., min_length=4, max_length=10)
    player_name: str = Field(default="Black", min_length=1, max_length=30)

class ClassicPlayerRequest(BaseModel):
    player_id: str = Field(..., min_length=20, max_length=100)


class ClassicGame:
    def __init__(self, time_control: str, started: bool):
        if time_control not in TIME_CONTROLS:
            raise ValueError("Unsupported time control")
        self.board = chess.Board()
        self.time_control = time_control
        initial, _ = TIME_CONTROLS[time_control]
        self.clocks = {"white": initial, "black": initial}
        self.clock_started_at: Optional[float] = time.time() if started and initial is not None else None
        self.moves: list[Dict[str, str]] = []
        self.captured = {"white": [], "black": []}
        self.result: Optional[str] = None
        self.termination: Optional[str] = None
        self.draw_offer: Optional[str] = None

    @classmethod
    def restore(cls, saved: Dict[str, Any], time_control: str) -> "ClassicGame":
        game = cls(time_control, started=False)
        for record in saved.get("moves", []):
            move = chess.Move.from_uci(record["uci"])
            if move not in game.board.legal_moves:
                raise ValueError("Stored classic game contains an illegal move")
            game.board.push(move)
            game.moves.append({"uci": record["uci"], "san": record["san"]})
        game.clocks = {
            "white": saved["clocks"]["white"],
            "black": saved["clocks"]["black"],
        }
        game.clock_started_at = saved.get("clock_started_at")
        game.captured = saved.get("captured", {"white": [], "black": []})
        game.result = saved.get("result")
        game.termination = saved.get("termination")
        game.draw_offer = saved.get("draw_offer")
        return game

    def _clock_values(self, now: Optional[float] = None) -> Dict[str, Optional[float]]:
        values = dict(self.clocks)
        if self.clock_started_at is not None and not self.result:
            color = "white" if self.board.turn else "black"
            remaining = values[color]
            if remaining is not None:
                values[color] = max(0.0, remaining - ((now or time.time()) - self.clock_started_at))
        return {
            side: None if value is None else round(value, 1)
            for side, value in values.items()
        }

    def _finish(self, result: str, termination: str, now: Optional[float] = None) -> None:
        self.clocks = self._clock_values(now)
        self.clock_started_at = None
        self.result = result
        self.termination = termination
        self.draw_offer = None

    def _check_end_conditions(self, now: Optional[float] = None) -> None:
        if self.result:
            return
        clocks = self._clock_values(now)
        active = "white" if self.board.turn else "black"
        remaining = clocks[active]
        if remaining is not None and remaining <= 0:
            opponent = "black" if active == "white" else "white"
            result = "1/2-1/2" if self.board.has_insufficient_material(opponent == "white") else (
                "0-1" if active == "white" else "1-0"
            )
            self._finish(result, "timeout", now)
            return
        outcome = self.board.outcome(claim_draw=False)
        if outcome:
            self._finish(outcome.result(), outcome.termination.name.lower(), now)

    def claim_draw(self) -> None:
        self._check_end_conditions()
        if self.result:
            raise ValueError("The game is already over")
        if self.board.can_claim_threefold_repetition():
            self._finish("1/2-1/2", "threefold_repetition")
        elif self.board.can_claim_fifty_moves():
            self._finish("1/2-1/2", "fifty_moves")
        else:
            raise ValueError("No threefold-repetition or fifty-move draw is available")

    def play(self, source: str, target: str, promotion: Optional[str]) -> None:
        self._check_end_conditions()
        if self.result:
            raise ValueError("The game is already over")
        if not isinstance(source, str) or not isinstance(target, str) or len(source) != 2 or len(target) != 2:
            raise ValueError("Squares must use algebraic notation")
        if promotion is not None and not isinstance(promotion, str):
            raise ValueError("Promotion must be queen, rook, bishop, or knight")
        promotion_types = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}
        if promotion is not None and promotion.lower() not in promotion_types:
            raise ValueError("Promotion must be queen, rook, bishop, or knight")
        move = chess.Move(
            chess.parse_square(source.lower()),
            chess.parse_square(target.lower()),
            promotion=promotion_types.get(promotion.lower()) if promotion else None,
        )
        if move not in self.board.legal_moves:
            raise ValueError("Illegal chess move")

        moving_side = "white" if self.board.turn else "black"
        captured_piece = self.board.piece_at(move.to_square)
        if self.board.is_en_passant(move):
            captured_piece = chess.Piece(chess.PAWN, not self.board.turn)
        san = self.board.san(move)
        now = time.time()
        self.clocks = self._clock_values(now)
        self.board.push(move)
        self.moves.append({"uci": move.uci(), "san": san})
        if captured_piece:
            self.captured[moving_side].append(chess.piece_symbol(captured_piece.piece_type))
        increment = TIME_CONTROLS[self.time_control][1]
        if self.clocks[moving_side] is not None:
            self.clocks[moving_side] += increment
        self.clock_started_at = now if any(value is not None for value in self.clocks.values()) else None
        self.draw_offer = None
        self._check_end_conditions(now)

    def snapshot(self, now: Optional[float] = None) -> Dict[str, Any]:
        self._check_end_conditions(now)
        return {
            "fen": self.board.fen(),
            "turn": "white" if self.board.turn else "black",
            "in_check": self.board.is_check(),
            "status": "COMPLETED" if self.result else "PLAYING",
            "result": self.result,
            "termination": self.termination,
            "moves": self.moves,
            "legal_moves": [
                {"from": chess.square_name(move.from_square), "to": chess.square_name(move.to_square),
                 "promotion": chess.piece_symbol(move.promotion) if move.promotion else None}
                for move in self.board.legal_moves
            ],
            "captured": self.captured,
            "clocks": self._clock_values(now),
            "draw_offer": self.draw_offer,
            "can_claim_draw": self.board.can_claim_threefold_repetition() or self.board.can_claim_fifty_moves(),
            "last_mover": ("black" if self.board.turn else "white") if self.moves else None,
        }

    def serialize(self) -> Dict[str, Any]:
        now = time.time()
        clocks = self._clock_values(now)
        return {
            "moves": self.moves,
            "clocks": clocks,
            "clock_started_at": now if self.clock_started_at is not None and not self.result else None,
            "captured": self.captured,
            "result": self.result,
            "termination": self.termination,
            "draw_offer": self.draw_offer,
        }


def _sanitize_players(players: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    return {
        side: {
            "side": side,
            "name": player["name"],
            "connected": player.get("connected", False),
            "ready": player.get("ready", False),
            "host": player.get("host", False),
        }
        for side, player in players.items()
    }


def _runtime(db: Session, code: str) -> Optional[Dict[str, Any]]:
    if code in classic_rooms:
        return classic_rooms[code]
    record = db.query(ClassicRoomModel).filter(ClassicRoomModel.room_code == code).first()
    if record is None:
        return None
    try:
        players = json.loads(record.players_json or "{}")
        state = json.loads(record.state_json or "{}")
    except json.JSONDecodeError as error:
        logger.exception("Could not decode saved classic room %s", code)
        raise HTTPException(status_code=500, detail="Saved classic room data is invalid") from error
    try:
        game = ClassicGame.restore(state, record.time_control)
    except (KeyError, TypeError, ValueError, chess.InvalidMoveError) as error:
        logger.exception("Could not restore classic game %s", code)
        raise HTTPException(status_code=500, detail="Saved classic game state is invalid") from error
    room = {
        "mode": record.mode,
        "time_control": record.time_control,
        "status": record.status,
        "players": players,
        "game": game,
        "is_private": record.is_private,
    }
    classic_rooms[code] = room
    return room


def _persist(db: Session, code: str, room: Dict[str, Any]) -> None:
    record = db.query(ClassicRoomModel).filter(ClassicRoomModel.room_code == code).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Classic room not found")
    snapshot = room["game"].snapshot()
    if snapshot["status"] == "COMPLETED":
        room["status"] = "COMPLETED"
    else:
        room["status"] = "PLAYING" if room["mode"] == "local" else room["status"]
    record.status = room["status"]
    record.players_json = json.dumps(room["players"])
    record.state_json = json.dumps(room["game"].serialize())
    db.commit()


def _public_state(code: str, room: Dict[str, Any]) -> Dict[str, Any]:
    server_time = time.time()
    game_state = room["game"].snapshot(server_time)
    if room["status"] == "WAITING":
        game_state["status"] = "WAITING"
    return {
        "room_code": code,
        "server_time": server_time,
        "mode": room["mode"],
        "time_control": room["time_control"],
        "settings": {
            "game_mode": "classic",
            "is_private": room.get("is_private", True),
            "time_control": room["time_control"],
            "max_players": 2,
        },
        "host_side": next(
            (side for side, player in room["players"].items() if player.get("host")),
            None,
        ),
        "status": game_state["status"] if room["mode"] == "local" or len(room["players"]) == 2 else "WAITING",
        "players": _sanitize_players(room["players"]),
        "game_state": game_state,
    }


def _player_side(players: Dict[str, Dict[str, Any]], player_id: str) -> Optional[str]:
    return next((side for side, player in players.items() if player["player_id"] == player_id), None)


def _generate_code(db: Session) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(ROOM_CODE_CHARS) for _ in range(ROOM_CODE_LENGTH))
        existing_classic = db.query(ClassicRoomModel.id).filter(ClassicRoomModel.room_code == code).first()
        from app.db import RoomModel
        existing_four_player = db.query(RoomModel.id).filter(RoomModel.room_code == code).first()
        if existing_classic is None and existing_four_player is None:
            return code
    raise HTTPException(status_code=503, detail="Could not allocate a unique room code")


@router.post("/classic/rooms")
def create_classic_room(
    request: CreateClassicRoomRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    enforce_room_rate_limit(http_request, "classic-create")
    mode = request.mode.strip().lower()
    if mode not in {"online", "local"}:
        raise HTTPException(status_code=422, detail="Mode must be local or online")
    control = request.time_control.strip().lower()
    if control not in TIME_CONTROLS:
        raise HTTPException(status_code=422, detail="Unsupported time control")

    code = _generate_code(db)
    white_id = str(uuid.uuid4())
    started = mode == "local"
    game = ClassicGame(control, started)
    players = {
        "white": {
            "player_id": white_id,
            "name": request.player_name.strip() or "White",
            "connected": False,
            "ready": True,
            "host": True,
        }
    }
    if started:
        players["black"] = {"player_id": white_id, "name": "Black", "connected": False, "ready": True}
    room = {"mode": mode, "time_control": control, "status": "PLAYING" if started else "WAITING",
            "players": players, "game": game, "is_private": request.is_private}
    classic_rooms[code] = room
    record = ClassicRoomModel(
        room_code=code, mode=mode, time_control=control, status=room["status"],
        players_json=json.dumps(players), state_json=json.dumps(game.serialize()),
        is_private=request.is_private,
    )
    db.add(record)
    db.commit()
    return {
        **_public_state(code, room),
        "player_id": white_id,
        "your_side": "white",
    }


@router.post("/classic/rooms/join")
async def join_classic_room(
    request: JoinClassicRoomRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    enforce_room_rate_limit(http_request, "classic-join", limit=20)
    code = request.room_code.strip().upper()
    room = _runtime(db, code)
    if room is None:
        raise HTTPException(status_code=404, detail="Classic room not found")
    if room["mode"] != "online":
        raise HTTPException(status_code=400, detail="Local rooms cannot be joined online")
    if room["status"] != "WAITING" or "black" in room["players"]:
        raise HTTPException(status_code=400, detail="Classic room is full or already started")

    black_id = str(uuid.uuid4())
    room["players"]["black"] = {
        "player_id": black_id, "name": request.player_name.strip() or "Black",
        "connected": False, "ready": False, "host": False,
    }
    _persist(db, code, room)
    await manager.broadcast_to_room(f"classic:{code}", {
        "type": "PLAYER_JOINED", "players": _sanitize_players(room["players"]),
        **_public_state(code, room),
    })
    return {**_public_state(code, room), "player_id": black_id, "your_side": "black"}


@router.post("/classic/rooms/{room_code}/start")
async def start_classic_room(room_code: str, request: ClassicPlayerRequest, db: Session = Depends(get_db)):
    code = room_code.strip().upper()
    room = _runtime(db, code)
    if room is None:
        raise HTTPException(status_code=404, detail="Classic room not found")
    side = _player_side(room["players"], request.player_id)
    if side is None:
        raise HTTPException(status_code=403, detail="Unauthorized player")
    if not room["players"][side].get("host"):
        raise HTTPException(status_code=403, detail="Only the room host can start the game")
    if room["status"] != "WAITING":
        raise HTTPException(status_code=400, detail="The game has already started")
    if room["mode"] != "online" or len(room["players"]) != 2:
        raise HTTPException(status_code=400, detail="Both player seats must be filled before starting")
    room["status"] = "PLAYING"
    if room["game"].clock_started_at is None and room["game"].clocks["white"] is not None:
        room["game"].clock_started_at = time.time()
    _persist(db, code, room)
    await manager.broadcast_to_room(f"classic:{code}", {
        "type": "GAME_STATE", "event": "START_GAME", **_public_state(code, room),
    })
    return {"success": True, **_public_state(code, room)}


@router.post("/classic/rooms/{room_code}/leave")
async def leave_classic_room(room_code: str, request: ClassicPlayerRequest, db: Session = Depends(get_db)):
    code = room_code.strip().upper()
    room = _runtime(db, code)
    if room is None:
        raise HTTPException(status_code=404, detail="Classic room not found")
    side = _player_side(room["players"], request.player_id)
    if side is None:
        raise HTTPException(status_code=403, detail="Unauthorized player")
    if room["status"] != "WAITING":
        raise HTTPException(status_code=400, detail="Started games must be resigned rather than left")
    leaving_player_id = room["players"][side]["player_id"]
    del room["players"][side]
    record = db.query(ClassicRoomModel).filter(ClassicRoomModel.room_code == code).first()
    if not room["players"]:
        db.delete(record)
        db.commit()
        classic_rooms.pop(code, None)
    else:
        if side == "white" and "black" in room["players"]:
            room["players"]["black"]["host"] = True
        _persist(db, code, room)
        await manager.broadcast_to_room(f"classic:{code}", {
            "type": "PLAYER_LEFT", **_public_state(code, room),
        })
    await manager.close_player_connection(f"classic:{code}", leaving_player_id)
    return {"success": True}


@router.get("/classic/rooms/{room_code}")
def get_classic_room(
    room_code: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    code = room_code.strip().upper()
    room = _runtime(db, code)
    if room is None:
        raise HTTPException(status_code=404, detail="Classic room not found")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Player authorization is required")
    player_id = authorization[7:]
    side = _player_side(room["players"], player_id)
    if side is None:
        raise HTTPException(status_code=403, detail="Unauthorized player")
    _persist(db, code, room)
    return {**_public_state(code, room), "your_side": side}


@router.websocket("/ws/classic/{room_code}")
async def classic_websocket(
    websocket: WebSocket,
    room_code: str,
    db: Session = Depends(get_db),
):
    code = room_code.strip().upper()
    room = _runtime(db, code)
    if room is None:
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
    player_id = (
        auth_payload.get("player_id")
        if isinstance(auth_payload, dict) and auth_payload.get("type") == "AUTH"
        else None
    )
    side = _player_side(room["players"], player_id or "")
    if side is None or not isinstance(player_id, str):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    manager_room = f"classic:{code}"
    await manager.connect(manager_room, player_id, websocket, accepted=True)
    room["players"][side]["connected"] = True
    _persist(db, code, room)
    await manager.send_personal_message(manager_room, player_id, {
        "type": "SYNC_STATE", "your_side": side, **_public_state(code, room),
    })
    await manager.broadcast_to_room(manager_room, {
        "type": "PRESENCE_UPDATE", **_public_state(code, room),
    })
    try:
        message_times: list[float] = []
        while True:
            try:
                raw_message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                previous_result = room["game"].result
                room["game"]._check_end_conditions()
                if room["game"].result and not previous_result:
                    _persist(db, code, room)
                    await manager.broadcast_to_room(manager_room, {
                        "type": "GAME_STATE", "event": "TIMEOUT", **_public_state(code, room),
                    })
                continue
            if len(raw_message) > 4096:
                    await manager.send_personal_message(manager_room, player_id, {
                        "type": "ERROR", "message": "Message is too large",
                    })
                    continue
            now = time.monotonic()
            message_times = [timestamp for timestamp in message_times if now - timestamp <= 10]
            if len(message_times) >= 60:
                    await manager.send_personal_message(manager_room, player_id, {
                        "type": "ERROR", "message": "Message rate limit exceeded",
                    })
                    continue
            message_times.append(now)
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await manager.send_personal_message(manager_room, player_id, {
                    "type": "ERROR", "message": "Invalid message format",
                })
                continue
            if not isinstance(payload, dict):
                await manager.send_personal_message(manager_room, player_id, {
                    "type": "ERROR", "message": "Message must be a JSON object",
                })
                continue
            message_type = payload.get("type")
            try:
                previous_result = room["game"].result
                room["game"]._check_end_conditions()
                if room["game"].result and not previous_result:
                    _persist(db, code, room)
                    await manager.broadcast_to_room(manager_room, {
                        "type": "GAME_STATE", "event": "TIMEOUT", **_public_state(code, room),
                    })
                    if message_type == "PING":
                        await manager.send_personal_message(manager_room, player_id, {
                            "type": "PONG", "server_time": time.time(),
                        })
                    else:
                        await manager.send_personal_message(manager_room, player_id, {
                            "type": "ERROR", "message": "The game is already over",
                        })
                    continue
                if message_type == "PING":
                    await manager.send_personal_message(manager_room, player_id, {
                        "type": "PONG", "server_time": time.time(),
                    })
                    continue
                if message_type == "START_GAME":
                    if not room["players"][side].get("host"):
                        raise PermissionError("Only the room host can start the game")
                    if room["status"] != "WAITING":
                        raise ValueError("The game has already started")
                    if room["mode"] != "online" or len(room["players"]) != 2:
                        raise ValueError("Both player seats must be filled before starting")
                    room["status"] = "PLAYING"
                    if room["game"].clock_started_at is None and room["game"].clocks["white"] is not None:
                        room["game"].clock_started_at = time.time()
                elif message_type == "READY":
                    if room["status"] != "WAITING":
                        raise ValueError("The room is no longer waiting")
                    room["players"][side]["ready"] = payload.get("ready") is True
                elif message_type == "MOVE":
                    current_side = "white" if room["game"].board.turn else "black"
                    if room["mode"] != "local" and side != current_side:
                        raise PermissionError("Not your turn")
                    if room["status"] != "PLAYING":
                        raise ValueError("The game has not started")
                    room["game"].play(payload.get("from", ""), payload.get("to", ""), payload.get("promotion"))
                elif message_type == "RESIGN":
                    if room["status"] != "PLAYING":
                        raise ValueError("The game is not active")
                    resigning_side = ("white" if room["game"].board.turn else "black") if room["mode"] == "local" else side
                    room["game"]._finish("0-1" if resigning_side == "white" else "1-0", "resignation")
                elif message_type == "CLAIM_DRAW":
                    current_side = "white" if room["game"].board.turn else "black"
                    if room["status"] != "PLAYING":
                        raise ValueError("The game is not active")
                    if room["mode"] != "local" and side != current_side:
                        raise PermissionError("Only the player whose turn it is can claim a draw")
                    room["game"].claim_draw()
                elif message_type == "OFFER_DRAW":
                    if room["status"] != "PLAYING":
                        raise ValueError("The game is not active")
                    last_mover = "black" if room["game"].board.turn else "white"
                    if not room["game"].moves or (room["mode"] != "local" and side != last_mover):
                        raise PermissionError("Only the player who just moved can offer a draw")
                    if room["game"].draw_offer:
                        raise ValueError("A draw offer is already pending")
                    room["game"].draw_offer = last_mover
                elif message_type == "ACCEPT_DRAW":
                    if room["mode"] != "local" and room["game"].draw_offer != ("black" if side == "white" else "white"):
                        raise PermissionError("There is no draw offer from your opponent")
                    if room["mode"] == "local" and not room["game"].draw_offer:
                        raise PermissionError("There is no draw offer")
                    room["game"]._finish("1/2-1/2", "agreement")
                elif message_type == "DECLINE_DRAW":
                    if room["mode"] != "local" and room["game"].draw_offer != ("black" if side == "white" else "white"):
                        raise PermissionError("There is no draw offer from your opponent")
                    if room["mode"] == "local" and not room["game"].draw_offer:
                        raise PermissionError("There is no draw offer")
                    room["game"].draw_offer = None
                else:
                    raise ValueError("Unsupported action")
                _persist(db, code, room)
                await manager.broadcast_to_room(manager_room, {
                    "type": "GAME_STATE", "event": message_type, **_public_state(code, room),
                })
            except PermissionError as error:
                await manager.send_personal_message(manager_room, player_id, {
                    "type": "ERROR", "message": str(error),
                })
            except (TypeError, ValueError, chess.InvalidMoveError) as error:
                await manager.send_personal_message(manager_room, player_id, {
                    "type": "ERROR", "message": str(error),
                })
    except WebSocketDisconnect:
        manager.disconnect(manager_room, player_id, websocket)
        if manager.is_player_connected(manager_room, player_id):
            return
        if side in room["players"]:
            room["players"][side]["connected"] = False
            _persist(db, code, room)
            await manager.broadcast_to_room(manager_room, {
                "type": "PRESENCE_UPDATE", **_public_state(code, room),
            })
