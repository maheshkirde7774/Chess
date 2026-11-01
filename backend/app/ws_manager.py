"""
WebSocket Connection Manager for Neon Four Chess
Handles active room connections, player authentication, disconnections, and real-time broadcasting.
"""

from typing import Dict, Any, Optional
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger("ws_manager")

class ConnectionManager:
    def __init__(self):
        # Mapping: room_code -> {player_id: WebSocket}
        self.room_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, room_code: str, player_id: str, websocket: WebSocket, accepted: bool = False):
        if not accepted:
            await websocket.accept()
        if room_code not in self.room_connections:
            self.room_connections[room_code] = {}
        previous = self.room_connections[room_code].get(player_id)
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=4001, reason="Session reconnected")
            except Exception:
                logger.warning("Could not close a superseded player connection in room %s", room_code)
        self.room_connections[room_code][player_id] = websocket
        logger.info("A player connected to room %s. Active connections: %s", room_code, len(self.room_connections[room_code]))

    def disconnect(self, room_code: str, player_id: str, websocket: Optional[WebSocket] = None):
        if room_code in self.room_connections:
            if player_id in self.room_connections[room_code] and (
                websocket is None or self.room_connections[room_code][player_id] is websocket
            ):
                del self.room_connections[room_code][player_id]
                logger.info("A player disconnected from room %s", room_code)
            if not self.room_connections[room_code]:
                del self.room_connections[room_code]

    def is_player_connected(self, room_code: str, player_id: str) -> bool:
        return room_code in self.room_connections and player_id in self.room_connections[room_code]

    async def close_player_connection(self, room_code: str, player_id: str):
        websocket = self.room_connections.get(room_code, {}).get(player_id)
        if websocket is not None:
            try:
                await websocket.close(code=1000, reason="Player left the room")
            except Exception:
                logger.warning("Could not close a departing player connection in room %s", room_code)
            self.disconnect(room_code, player_id, websocket)

    async def send_personal_message(self, room_code: str, player_id: str, message: Dict[str, Any]):
        if room_code in self.room_connections and player_id in self.room_connections[room_code]:
            try:
                ws = self.room_connections[room_code][player_id]
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.error("Error sending room message in %s: %s", room_code, e)

    async def broadcast_to_room(self, room_code: str, message: Dict[str, Any]):
        if room_code in self.room_connections:
            text_data = json.dumps(message)
            dead_connections = []
            for player_id, ws in list(self.room_connections[room_code].items()):
                try:
                    await ws.send_text(text_data)
                except Exception as e:
                    logger.warning("Failed to send room message in %s: %s", room_code, e)
                    dead_connections.append(player_id)

            for dead_id in dead_connections:
                self.disconnect(room_code, dead_id)


manager = ConnectionManager()
