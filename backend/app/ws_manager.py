"""
WebSocket Connection Manager for Neon Four Chess
Handles active room connections, player authentication, disconnections, and real-time broadcasting.
"""

import asyncio
from typing import Dict, Any, Optional
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger("ws_manager")

class ConnectionManager:
    def __init__(self):
        # Mapping: room_code -> {player_id: WebSocket}
        self.room_connections: Dict[str, Dict[str, WebSocket]] = {}
        self.spectator_connections: Dict[str, Dict[str, tuple[WebSocket, str]]] = {}
        self.max_spectators_per_room = 100
        self.max_spectators_total = 500
        self.max_spectators_per_ip = 20

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
            if not self.room_connections[room_code] and not self.spectator_connections.get(room_code):
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
        connections = [
            (client_id, websocket, False)
            for client_id, websocket in self.room_connections.get(room_code, {}).items()
        ] + [
            (client_id, websocket, True)
            for client_id, (websocket, _) in self.spectator_connections.get(room_code, {}).items()
        ]
        if not connections:
            return

        text_data = json.dumps(message)

        async def send(client_id: str, websocket: WebSocket, spectator: bool):
            try:
                await asyncio.wait_for(websocket.send_text(text_data), timeout=1.5)
                return None
            except Exception as error:
                logger.warning("Failed to send room message in %s: %s", room_code, error)
                return client_id, websocket, spectator

        failed = await asyncio.gather(
            *(send(client_id, websocket, spectator)
              for client_id, websocket, spectator in connections)
        )
        spectator_disconnected = False
        for item in failed:
            if item is None:
                continue
            client_id, websocket, spectator = item
            if spectator:
                self.disconnect_spectator(room_code, client_id, websocket)
                spectator_disconnected = True
            else:
                self.disconnect(room_code, client_id, websocket)
        game_state = message.get("game_state")
        completed = (
            message.get("status") == "COMPLETED"
            or message.get("is_game_over") is True
            or isinstance(game_state, dict) and (
                game_state.get("status") == "COMPLETED"
                or game_state.get("is_game_over") is True
            )
        )
        if completed and self.spectator_count(room_code):
            await self.close_spectators(room_code)
            await self.broadcast_to_room(room_code, {
                "type": "SPECTATOR_COUNT",
                "spectator_count": 0,
            })
        elif spectator_disconnected:
            count_text = json.dumps({
                "type": "SPECTATOR_COUNT",
                "spectator_count": self.spectator_count(room_code),
            })

            async def notify_count(websocket: WebSocket):
                try:
                    await asyncio.wait_for(websocket.send_text(count_text), timeout=0.25)
                except Exception as error:
                    logger.warning("Could not send updated spectator count in %s: %s", room_code, error)

            remaining = [
                websocket
                for websocket in self.room_connections.get(room_code, {}).values()
            ] + [
                websocket
                for websocket, _ in self.spectator_connections.get(room_code, {}).values()
            ]
            await asyncio.gather(*(notify_count(websocket) for websocket in remaining))

    def spectator_count(self, room_code: str) -> int:
        return len(self.spectator_connections.get(room_code, {}))

    def spectator_count_for_ip(self, ip_address: str) -> int:
        return sum(
            1
            for connections in self.spectator_connections.values()
            for _, address in connections.values()
            if address == ip_address
        )

    async def connect_spectator(
        self,
        room_code: str,
        spectator_id: str,
        websocket: WebSocket,
        ip_address: str,
        accepted: bool = False,
    ) -> None:
        if self.spectator_count(room_code) >= self.max_spectators_per_room:
            raise ValueError("This match has reached its spectator limit")
        total = sum(len(connections) for connections in self.spectator_connections.values())
        if total >= self.max_spectators_total:
            raise ValueError("The server has reached its spectator limit")
        if self.spectator_count_for_ip(ip_address) >= self.max_spectators_per_ip:
            raise ValueError("Too many spectator connections from this address")
        if not accepted:
            await websocket.accept()
        self.room_connections.setdefault(room_code, {})
        self.spectator_connections.setdefault(room_code, {})[spectator_id] = (
            websocket, ip_address,
        )

    def disconnect_spectator(
        self,
        room_code: str,
        spectator_id: str,
        websocket: Optional[WebSocket] = None,
    ) -> None:
        connections = self.spectator_connections.get(room_code)
        if connections is None:
            return
        current = connections.get(spectator_id)
        if current is None or (websocket is not None and current[0] is not websocket):
            return
        del connections[spectator_id]
        if not connections:
            del self.spectator_connections[room_code]
        if not self.room_connections.get(room_code) and room_code in self.room_connections:
            del self.room_connections[room_code]

    async def close_spectators(self, room_code: str, reason: str = "Match completed") -> None:
        connections = list(self.spectator_connections.get(room_code, {}).items())
        for spectator_id, (websocket, _) in connections:
            try:
                await websocket.close(code=1000, reason=reason)
            except Exception as error:
                logger.warning("Could not close spectator connection in %s: %s", room_code, error)
            self.disconnect_spectator(room_code, spectator_id, websocket)


manager = ConnectionManager()
