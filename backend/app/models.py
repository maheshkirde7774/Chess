"""
Pydantic Schemas for Neon Four Chess API
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class CreateRoomRequest(BaseModel):
    player_name: str = Field(default="Player 1", min_length=1, max_length=30)

class CreateRoomResponse(BaseModel):
    room_code: str
    player_id: str
    player_role: int
    player_name: str
    message: str

class JoinRoomRequest(BaseModel):
    room_code: str = Field(..., min_length=4, max_length=10)
    player_name: str = Field(default="Guest", min_length=1, max_length=30)

class JoinRoomResponse(BaseModel):
    room_code: str
    player_id: str
    player_role: int
    player_name: str
    message: str

class MoveRequest(BaseModel):
    player_id: str
    from_sq: List[int] = Field(..., min_length=2, max_length=2)
    to_sq: List[int] = Field(..., min_length=2, max_length=2)
    promotion: Optional[str] = None

class ResignRequest(BaseModel):
    player_id: str

class RoomStateResponse(BaseModel):
    room_code: str
    status: str
    current_turn: int
    active_players: List[int]
    players: Dict[str, Any]
    game_state: Dict[str, Any]
    winner: Optional[int] = None
