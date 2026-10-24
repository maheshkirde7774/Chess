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

    async def connect(self, room_code: str, player_id: str, websocket: WebSocket):
        await websocket.accept()
        if room_code not in self.room_connections:
            self.room_connections[room_code] = {}
        self.room_connections[room_code][player_id] = websocket
        logger.info(f"Player {player_id} connected to room {room_code}. Active connections: {len(self.room_connections[room_code])}")

    def disconnect(self, room_code: str, player_id: str):
        if room_code in self.room_connections:
            if player_id in self.room_connections[room_code]:
                del self.room_connections[room_code][player_id]
                logger.info(f"Player {player_id} disconnected from room {room_code}")
            if not self.room_connections[room_code]:
                del self.room_connections[room_code]

    def is_player_connected(self, room_code: str, player_id: str) -> bool:
        return room_code in self.room_connections and player_id in self.room_connections[room_code]

    async def send_personal_message(self, room_code: str, player_id: str, message: Dict[str, Any]):
        if room_code in self.room_connections and player_id in self.room_connections[room_code]:
            try:
                ws = self.room_connections[room_code][player_id]
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {player_id} in {room_code}: {e}")

    async def broadcast_to_room(self, room_code: str, message: Dict[str, Any]):
        if room_code in self.room_connections:
            text_data = json.dumps(message)
            dead_connections = []
            for player_id, ws in list(self.room_connections[room_code].items()):
                try:
                    await ws.send_text(text_data)
                except Exception as e:
                    logger.warning(f"Failed to send to player {player_id} in {room_code}: {e}")
                    dead_connections.append(player_id)

            for dead_id in dead_connections:
                self.disconnect(room_code, dead_id)


manager = ConnectionManager()
