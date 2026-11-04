"""
Pydantic Schemas for Neon Four Chess API
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field, conint

class CreateRoomRequest(BaseModel):
    player_name: str = Field(default="Player 1", min_length=1, max_length=30)
    is_private: bool = True
    time_control: str = Field(default="unlimited", min_length=1, max_length=10)

class CreateRoomResponse(BaseModel):
    room_code: str
    player_id: str
    player_role: int
    player_name: str
    message: str
    spectator_token: Optional[str] = None

class JoinRoomRequest(BaseModel):
    room_code: str = Field(..., min_length=4, max_length=10)
    player_name: str = Field(default="Guest", min_length=1, max_length=30)

class JoinRoomResponse(BaseModel):
    room_code: str
    player_id: str
    player_role: int
    player_name: str
    message: str
    spectator_token: Optional[str] = None

class MoveRequest(BaseModel):
    player_id: str
    from_sq: List[conint(strict=True, ge=0, le=13)] = Field(..., min_length=2, max_length=2)
    to_sq: List[conint(strict=True, ge=0, le=13)] = Field(..., min_length=2, max_length=2)
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
    settings: Dict[str, Any] = Field(default_factory=dict)
    host_role: Optional[int] = None
