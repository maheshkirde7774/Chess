"""Friend relationships, private messaging, presence, and game invitations."""

import asyncio
import json
import logging
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import (
    BlockedPlayerModel,
    ConversationModel,
    FriendRequestModel,
    FriendshipModel,
    GameInvitationModel,
    PlayerProfileModel,
    PlayerReportModel,
    PrivateMessageModel,
    SocialNotificationModel,
    get_db,
    get_utc_now,
)
from app.profiles import profile_from_authorization

logger = logging.getLogger("fourx_social")
router = APIRouter()

_rate_lock = threading.Lock()
_social_attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_SOCIAL_RATE_LIMITS = {
    "friend_request": (15, 3600),
    "message": (30, 60),
    "invitation": (8, 3600),
    "report": (5, 86400),
}


class FriendRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: str = Field(min_length=36, max_length=36)


class MessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message cannot be blank")
        if any(ord(character) < 32 and character not in "\n\t" for character in value):
            raise ValueError("Message contains unsupported control characters")
        return value


class InvitationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: str = Field(min_length=36, max_length=36)
    game_mode: str

    @field_validator("game_mode")
    @classmethod
    def validate_game_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"classic", "four_player"}:
            raise ValueError("Game mode must be classic or four_player")
        return normalized


class ReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    player_id: str = Field(min_length=36, max_length=36)
    category: str = Field(min_length=3, max_length=24)
    details: str = Field(default="", max_length=1000)

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        allowed = {"harassment", "spam", "inappropriate", "other"}
        normalized = value.strip().lower()
        if normalized not in allowed:
            raise ValueError("Choose harassment, spam, inappropriate, or other")
        return normalized

    @field_validator("details")
    @classmethod
    def validate_details(cls, value: str) -> str:
        value = value.strip()
        if any(ord(character) < 32 and character not in "\n\t" for character in value):
            raise ValueError("Report details contain unsupported control characters")
        return value


def _pair_key(first_id: str, second_id: str) -> str:
    return ":".join(sorted((first_id, second_id)))


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _authorized_profile(authorization: Optional[str], db: Session) -> PlayerProfileModel:
    profile = profile_from_authorization(authorization, db)
    if profile is None:
        raise HTTPException(status_code=401, detail="A device profile credential is required")
    return profile


def _apply_rate_limit(profile_id: str, action: str) -> None:
    limit, window = _SOCIAL_RATE_LIMITS[action]
    now = time.monotonic()
    key = (profile_id, action)
    with _rate_lock:
        attempts = _social_attempts[key]
        while attempts and now - attempts[0] >= window:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(status_code=429, detail="Too many social actions. Please try again later.")
        attempts.append(now)


def _friendship(db: Session, first_id: str, second_id: str) -> Optional[FriendshipModel]:
    return db.query(FriendshipModel).filter(
        FriendshipModel.pair_key == _pair_key(first_id, second_id)
    ).first()


def _blocked(db: Session, first_id: str, second_id: str) -> bool:
    return db.query(BlockedPlayerModel.id).filter(
        or_(
            (BlockedPlayerModel.blocker_id == first_id) & (BlockedPlayerModel.blocked_id == second_id),
            (BlockedPlayerModel.blocker_id == second_id) & (BlockedPlayerModel.blocked_id == first_id),
        )
    ).first() is not None


def _active_profile(db: Session, profile_id: str) -> Optional[PlayerProfileModel]:
    return db.query(PlayerProfileModel).filter(
        PlayerProfileModel.id == profile_id,
        PlayerProfileModel.is_suspended.is_(False),
        PlayerProfileModel.deleted_at.is_(None),
    ).first()


def _notify(
    db: Session,
    recipient_id: str,
    actor_id: Optional[str],
    notification_type: str,
    dedupe_key: str,
    payload: dict[str, Any],
) -> SocialNotificationModel:
    existing = db.query(SocialNotificationModel).filter(
        SocialNotificationModel.dedupe_key == dedupe_key
    ).first()
    if existing is not None:
        return existing
    notification = SocialNotificationModel(
        recipient_id=recipient_id,
        actor_id=actor_id,
        notification_type=notification_type,
        dedupe_key=dedupe_key,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(notification)
    return notification


def _notification_payload(
    db: Session, notification: SocialNotificationModel
) -> dict[str, Any]:
    actor = _active_profile(db, notification.actor_id) if notification.actor_id else None
    try:
        payload = json.loads(notification.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        logger.warning("Stored social notification %s has invalid JSON", notification.id)
        payload = {}
    return {
        "id": notification.id,
        "type": notification.notification_type,
        "actor": {"id": actor.id, "username": actor.username} if actor else None,
        "payload": payload,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
    }


def _profile_summary(profile: PlayerProfileModel) -> dict[str, str]:
    return {"id": profile.id, "username": profile.username, "avatar": profile.avatar}


def _request_payload(
    db: Session, request: FriendRequestModel, viewer_id: str
) -> dict[str, Any]:
    other_id = (
        request.addressee_id
        if request.requester_id == viewer_id
        else request.requester_id
    )
    other = _active_profile(db, other_id)
    return {
        "id": request.id,
        "player": _profile_summary(other) if other else None,
        "created_at": request.created_at.isoformat() if request.created_at else None,
    }


def _friend_ids(db: Session, profile_id: str) -> list[str]:
    rows = db.query(FriendshipModel).filter(
        or_(
            FriendshipModel.player_low_id == profile_id,
            FriendshipModel.player_high_id == profile_id,
        )
    ).all()
    return [
        row.player_high_id if row.player_low_id == profile_id else row.player_low_id
        for row in rows
    ]


class PresenceHub:
    def __init__(self) -> None:
        self.connections: dict[str, WebSocket] = {}
        self.heartbeats: dict[str, float] = {}
        self.activity: dict[str, float] = {}
        self.game_rooms: dict[str, set[str]] = defaultdict(set)

    def status(self, profile_id: str, now: Optional[float] = None) -> str:
        current = time.monotonic() if now is None else now
        heartbeat = self.heartbeats.get(profile_id)
        if heartbeat is None or current - heartbeat > 45 or profile_id not in self.connections:
            return "offline"
        if self.game_rooms.get(profile_id):
            return "playing"
        if current - self.activity.get(profile_id, heartbeat) > 180:
            return "away"
        return "online"

    async def connect(self, profile_id: str, websocket: WebSocket, db: Session) -> None:
        previous_status = self.status(profile_id)
        previous = self.connections.get(profile_id)
        if previous is not None and previous is not websocket:
            try:
                await previous.close(code=4001, reason="Social session reconnected")
            except Exception:
                logger.debug("Superseded social socket already closed")
        self.connections[profile_id] = websocket
        now = time.monotonic()
        self.heartbeats[profile_id] = now
        self.activity[profile_id] = now
        if previous_status != self.status(profile_id):
            await self.broadcast_presence(profile_id, db)

    async def heartbeat(self, profile_id: str, active: bool, db: Session) -> None:
        before = self.status(profile_id)
        now = time.monotonic()
        self.heartbeats[profile_id] = now
        if active:
            self.activity[profile_id] = now
        if before != self.status(profile_id):
            await self.broadcast_presence(profile_id, db)

    async def disconnect(self, profile_id: str, websocket: WebSocket, db: Session) -> None:
        if self.connections.get(profile_id) is not websocket:
            return
        self.connections.pop(profile_id, None)
        self.heartbeats.pop(profile_id, None)
        self.activity.pop(profile_id, None)
        await self.broadcast_presence(profile_id, db)

    async def mark_game(self, profile_id: Optional[str], room_code: str, active: bool, db: Session) -> None:
        if not profile_id:
            return
        before = self.status(profile_id)
        if active:
            self.game_rooms[profile_id].add(room_code)
        else:
            self.game_rooms[profile_id].discard(room_code)
            if not self.game_rooms[profile_id]:
                self.game_rooms.pop(profile_id, None)
        if before != self.status(profile_id):
            await self.broadcast_presence(profile_id, db)

    async def send(self, profile_id: str, payload: dict[str, Any]) -> bool:
        websocket = self.connections.get(profile_id)
        if websocket is None or self.status(profile_id) == "offline":
            return False
        try:
            await websocket.send_json(payload)
            return True
        except Exception:
            logger.info("Could not deliver a social event to a disconnected profile")
            return False

    async def publish_notification(self, db: Session, notification: SocialNotificationModel) -> None:
        await self.send(notification.recipient_id, {
            "type": "NOTIFICATION",
            "notification": _notification_payload(db, notification),
        })

    async def broadcast_presence(self, profile_id: str, db: Session) -> None:
        event = {
            "type": "PRESENCE_UPDATE",
            "player_id": profile_id,
            "status": self.status(profile_id),
        }
        for friend_id in _friend_ids(db, profile_id):
            await self.send(friend_id, event)


presence_hub = PresenceHub()


def _conversation_for(db: Session, first_id: str, second_id: str) -> ConversationModel:
    key = _pair_key(first_id, second_id)
    conversation = db.query(ConversationModel).filter(ConversationModel.pair_key == key).first()
    if conversation is not None:
        return conversation
    ordered = sorted((first_id, second_id))
    conversation = ConversationModel(
        id=str(uuid.uuid4()),
        participant_a_id=ordered[0],
        participant_b_id=ordered[1],
        pair_key=key,
    )
    db.add(conversation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        conversation = db.query(ConversationModel).filter(
            ConversationModel.pair_key == key
        ).first()
        if conversation is None:
            raise HTTPException(status_code=503, detail="Could not open conversation")
    return conversation


def _conversation_member(conversation: ConversationModel, profile_id: str) -> bool:
    return profile_id in (conversation.participant_a_id, conversation.participant_b_id)


def _accessible_conversation(
    db: Session, conversation_id: str, profile_id: str
) -> tuple[ConversationModel, str]:
    conversation = db.query(ConversationModel).filter(
        ConversationModel.id == conversation_id
    ).first()
    if conversation is None or not _conversation_member(conversation, profile_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    other_id = (
        conversation.participant_b_id
        if conversation.participant_a_id == profile_id
        else conversation.participant_a_id
    )
    if not _friendship(db, profile_id, other_id) or _blocked(db, profile_id, other_id):
        raise HTTPException(status_code=403, detail="Messaging is unavailable for this player")
    if _active_profile(db, other_id) is None:
        raise HTTPException(status_code=404, detail="Conversation participant is unavailable")
    return conversation, other_id


def _message_payload(db: Session, message: PrivateMessageModel, viewer_id: str) -> dict[str, Any]:
    sender = _active_profile(db, message.sender_id)
    if message.sender_id == viewer_id:
        delivery = "read" if message.read_at else "delivered" if message.delivered_at else "sent"
    else:
        delivery = "received"
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": sender.username if sender else "Unavailable player",
        "content": message.content,
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "status": delivery,
    }


def _room_code(db: Session) -> str:
    from app.main import generate_room_code
    from app.db import ClassicRoomModel, RoomModel

    for _ in range(20):
        code = generate_room_code()
        if (
            db.query(RoomModel.id).filter(RoomModel.room_code == code).first() is None
            and db.query(ClassicRoomModel.id).filter(ClassicRoomModel.room_code == code).first() is None
        ):
            return code
    raise HTTPException(status_code=503, detail="Could not allocate a unique room code")


def _create_invitation_room(
    db: Session, invitation: GameInvitationModel, sender: PlayerProfileModel, recipient: PlayerProfileModel
) -> dict[str, Any]:
    if invitation.game_mode == "four_player":
        from app.engine import FourPlayerChessEngine, PLAYER_CYAN, PLAYER_MAGENTA
        from app.main import active_rooms
        from app.db import RoomModel

        code = _room_code(db)
        sender_player_id = secrets.token_urlsafe(32)
        recipient_player_id = secrets.token_urlsafe(32)
        engine = FourPlayerChessEngine()
        players = {
            PLAYER_CYAN: {
                "player_id": sender_player_id,
                "name": sender.username,
                "connected": False,
                "ready": True,
                "host": True,
                "profile_id": sender.id,
            },
            PLAYER_MAGENTA: {
                "player_id": recipient_player_id,
                "name": recipient.username,
                "connected": False,
                "ready": True,
                "host": False,
                "profile_id": recipient.id,
            },
        }
        settings = {
            "game_mode": "four_player",
            "is_private": True,
            "time_control": "unlimited",
            "max_players": 4,
        }
        active_rooms[code] = {
            "engine": engine,
            "players": players,
            "status": "WAITING",
            "match_id": str(uuid.uuid4()),
            "started_at": None,
            "settings": settings,
        }
        db.add(RoomModel(
            room_code=code,
            status="WAITING",
            players_json=json.dumps(players),
            state_json=json.dumps(engine.get_state()),
            settings_json=json.dumps(settings),
            match_id=active_rooms[code]["match_id"],
        ))
        db.flush()
        invitation.sender_player_id = sender_player_id
        invitation.recipient_player_id = recipient_player_id
        return {
            "game_mode": "four_player",
            "room_code": code,
            "player_id": recipient_player_id,
            "player_role": PLAYER_MAGENTA,
        }

    from app.classic import ClassicGame, _generate_code, _persist, _public_state, classic_rooms
    from app.db import ClassicRoomModel

    code = _generate_code(db)
    sender_player_id = secrets.token_urlsafe(32)
    recipient_player_id = secrets.token_urlsafe(32)
    now = get_utc_now()
    game = ClassicGame("10+0", started=False)
    players = {
        "white": {
            "player_id": sender_player_id,
            "name": sender.username,
            "connected": False,
            "ready": True,
            "host": True,
            "profile_id": sender.id,
        },
        "black": {
            "player_id": recipient_player_id,
            "name": recipient.username,
            "connected": False,
            "ready": True,
            "host": False,
            "profile_id": recipient.id,
        },
    }
    room = {
        "mode": "online",
        "time_control": "10+0",
        "status": "WAITING",
        "players": players,
        "game": game,
        "is_private": True,
        "match_id": str(uuid.uuid4()),
        "started_at": None,
        "ai": {},
        "ai_thinking": False,
        "generation": 0,
    }
    classic_rooms[code] = room
    db.add(ClassicRoomModel(
        room_code=code,
        mode="online",
        time_control="10+0",
        status="WAITING",
        players_json=json.dumps(players),
        state_json=json.dumps(game.serialize()),
        is_private=True,
        ai_config_json="{}",
        match_id=room["match_id"],
        started_at=None,
    ))
    db.flush()
    _persist(db, code, room)
    invitation.sender_player_id = sender_player_id
    invitation.recipient_player_id = recipient_player_id
    launch = _public_state(code, room)
    return {
        "game_mode": "classic",
        **launch,
        "player_id": recipient_player_id,
        "your_side": "black",
    }


@router.get("/api/social/dashboard")
def social_dashboard(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    friends = []
    for friend_id in _friend_ids(db, profile.id):
        friend = _active_profile(db, friend_id)
        if friend is not None and not _blocked(db, profile.id, friend_id):
            friends.append({
                **_profile_summary(friend),
                "status": presence_hub.status(friend.id),
            })
    friends.sort(key=lambda item: (item["status"] == "offline", item["username"].casefold()))

    incoming = db.query(FriendRequestModel).filter(
        FriendRequestModel.addressee_id == profile.id,
        FriendRequestModel.status == "pending",
    ).order_by(FriendRequestModel.created_at.desc()).all()
    outgoing = db.query(FriendRequestModel).filter(
        FriendRequestModel.requester_id == profile.id,
        FriendRequestModel.status == "pending",
    ).order_by(FriendRequestModel.created_at.desc()).all()

    conversations = db.query(ConversationModel).filter(
        or_(
            ConversationModel.participant_a_id == profile.id,
            ConversationModel.participant_b_id == profile.id,
        )
    ).all()
    chat_list = []
    for conversation in conversations:
        other_id = (
            conversation.participant_b_id
            if conversation.participant_a_id == profile.id
            else conversation.participant_a_id
        )
        other = _active_profile(db, other_id)
        if other is None or not _friendship(db, profile.id, other_id) or _blocked(db, profile.id, other_id):
            continue
        last_message = db.query(PrivateMessageModel).filter(
            PrivateMessageModel.conversation_id == conversation.id
        ).order_by(PrivateMessageModel.created_at.desc(), PrivateMessageModel.id.desc()).first()
        unread = db.query(PrivateMessageModel.id).filter(
            PrivateMessageModel.conversation_id == conversation.id,
            PrivateMessageModel.recipient_id == profile.id,
            PrivateMessageModel.read_at.is_(None),
        ).count()
        chat_list.append({
            "id": conversation.id,
            "player": {**_profile_summary(other), "status": presence_hub.status(other.id)},
            "unread": unread,
            "last_message": {
                "content": last_message.content,
                "created_at": last_message.created_at.isoformat() if last_message.created_at else None,
                "sender_id": last_message.sender_id,
            } if last_message else None,
        })
    chat_list.sort(
        key=lambda item: item["last_message"]["created_at"] if item["last_message"] else "",
        reverse=True,
    )

    invitations = db.query(GameInvitationModel).filter(
        GameInvitationModel.status == "pending",
        or_(
            GameInvitationModel.sender_id == profile.id,
            GameInvitationModel.recipient_id == profile.id,
        ),
    ).order_by(GameInvitationModel.created_at.desc()).all()
    invitation_items = []
    now = get_utc_now()
    for invite in invitations:
        if (_utc(invite.expires_at) or now) <= now:
            invite.status = "expired"
            invite.active_key = None
            continue
        other_id = invite.sender_id if invite.recipient_id == profile.id else invite.recipient_id
        other = _active_profile(db, other_id)
        invitation_items.append({
            "id": invite.id,
            "direction": "incoming" if invite.recipient_id == profile.id else "outgoing",
            "game_mode": invite.game_mode,
            "player": _profile_summary(other) if other else None,
            "created_at": invite.created_at.isoformat() if invite.created_at else None,
            "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
        })

    notifications = db.query(SocialNotificationModel).filter(
        SocialNotificationModel.recipient_id == profile.id
    ).order_by(SocialNotificationModel.created_at.desc()).limit(30).all()
    blocked_rows = db.query(BlockedPlayerModel).filter(
        BlockedPlayerModel.blocker_id == profile.id
    ).order_by(BlockedPlayerModel.created_at.desc()).all()
    blocked_players = []
    for blocked_row in blocked_rows:
        blocked_profile = _active_profile(db, blocked_row.blocked_id)
        if blocked_profile is not None:
            blocked_players.append(_profile_summary(blocked_profile))
    unread_notifications = db.query(SocialNotificationModel.id).filter(
        SocialNotificationModel.recipient_id == profile.id,
        SocialNotificationModel.read_at.is_(None),
    ).count()
    db.commit()
    return {
        "friends": friends,
        "incoming_requests": [
            item for request in incoming
            if (item := _request_payload(db, request, profile.id))["player"]
        ],
        "outgoing_requests": [
            item for request in outgoing
            if (item := _request_payload(db, request, profile.id))["player"]
        ],
        "conversations": chat_list,
        "invitations": invitation_items,
        "blocked_players": blocked_players,
        "notifications": [_notification_payload(db, item) for item in notifications],
        "unread_notifications": unread_notifications,
    }


@router.get("/api/social/players")
def search_players(
    q: str = Query(default="", max_length=24),
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    query = q.strip()
    if len(query) < 2:
        return []
    blocked_ids = {
        row[0] for row in db.query(BlockedPlayerModel.blocked_id).filter(
            BlockedPlayerModel.blocker_id == profile.id
        ).all()
    }
    blocked_ids.update(
        row[0] for row in db.query(BlockedPlayerModel.blocker_id).filter(
            BlockedPlayerModel.blocked_id == profile.id
        ).all()
    )
    escaped_query = query.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    matches = db.query(PlayerProfileModel).filter(
        PlayerProfileModel.username_key.like(f"%{escaped_query}%", escape="\\"),
        PlayerProfileModel.id != profile.id,
        PlayerProfileModel.is_suspended.is_(False),
        PlayerProfileModel.deleted_at.is_(None),
    ).order_by(PlayerProfileModel.username_key).limit(30).all()
    return [
        {**_profile_summary(player), "status": presence_hub.status(player.id)}
        for player in matches if player.id not in blocked_ids
    ]


@router.post("/api/social/requests")
async def send_friend_request(
    body: FriendRequestInput,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    _apply_rate_limit(profile.id, "friend_request")
    target = _active_profile(db, body.player_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if profile.id == target.id:
        raise HTTPException(status_code=400, detail="You cannot send a friend request to yourself")
    if _blocked(db, profile.id, target.id):
        raise HTTPException(status_code=403, detail="A block prevents this request")
    if _friendship(db, profile.id, target.id):
        raise HTTPException(status_code=409, detail="You are already friends")

    key = _pair_key(profile.id, target.id)
    friend_request = db.query(FriendRequestModel).filter(
        FriendRequestModel.pair_key == key
    ).first()
    if friend_request and friend_request.status == "pending":
        if friend_request.requester_id == profile.id:
            raise HTTPException(status_code=409, detail="Friend request is already pending")
        raise HTTPException(status_code=409, detail="This player already sent you a request")
    now = get_utc_now()
    if friend_request is None:
        friend_request = FriendRequestModel(
            requester_id=profile.id,
            addressee_id=target.id,
            pair_key=key,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        db.add(friend_request)
    else:
        friend_request.requester_id = profile.id
        friend_request.addressee_id = target.id
        friend_request.status = "pending"
        friend_request.created_at = now
        friend_request.updated_at = now
    db.flush()
    notification = _notify(
        db, target.id, profile.id, "friend_request",
        f"friend-request:{friend_request.id or key}:{now.timestamp()}",
        {"request_id": friend_request.id, "player_id": profile.id},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Friend request is already pending")
    await presence_hub.publish_notification(db, notification)
    return {"success": True, "request_id": friend_request.id}


@router.post("/api/social/requests/{request_id}/accept")
async def accept_friend_request(
    request_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    friend_request = db.query(FriendRequestModel).filter(
        FriendRequestModel.id == request_id,
        FriendRequestModel.addressee_id == profile.id,
        FriendRequestModel.status == "pending",
    ).first()
    if friend_request is None:
        raise HTTPException(status_code=404, detail="Pending friend request not found")
    sender = _active_profile(db, friend_request.requester_id)
    if sender is None or _blocked(db, profile.id, friend_request.requester_id):
        raise HTTPException(status_code=403, detail="This player is unavailable")
    now = get_utc_now()
    friend_request.status = "accepted"
    friend_request.updated_at = now
    relationship = FriendshipModel(
        player_low_id=min(profile.id, sender.id),
        player_high_id=max(profile.id, sender.id),
        pair_key=friend_request.pair_key,
    )
    db.add(relationship)
    notification = _notify(
        db, sender.id, profile.id, "friend_accepted",
        f"friend-accepted:{friend_request.id}",
        {"player_id": profile.id, "username": profile.username},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Friend request has already been handled")
    await presence_hub.publish_notification(db, notification)
    await presence_hub.broadcast_presence(profile.id, db)
    await presence_hub.broadcast_presence(sender.id, db)
    return {"success": True}


@router.post("/api/social/requests/{request_id}/reject")
def reject_friend_request(
    request_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    friend_request = db.query(FriendRequestModel).filter(
        FriendRequestModel.id == request_id,
        FriendRequestModel.addressee_id == profile.id,
        FriendRequestModel.status == "pending",
    ).first()
    if friend_request is None:
        raise HTTPException(status_code=404, detail="Pending friend request not found")
    friend_request.status = "rejected"
    friend_request.updated_at = get_utc_now()
    db.commit()
    return {"success": True}


@router.delete("/api/social/requests/{request_id}")
def cancel_friend_request(
    request_id: int,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    friend_request = db.query(FriendRequestModel).filter(
        FriendRequestModel.id == request_id,
        FriendRequestModel.requester_id == profile.id,
        FriendRequestModel.status == "pending",
    ).first()
    if friend_request is None:
        raise HTTPException(status_code=404, detail="Pending friend request not found")
    friend_request.status = "cancelled"
    friend_request.updated_at = get_utc_now()
    db.commit()
    return {"success": True}


@router.delete("/api/social/friends/{player_id}")
async def remove_friend(
    player_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    relationship = _friendship(db, profile.id, player_id)
    if relationship is None:
        raise HTTPException(status_code=404, detail="Friend not found")
    db.delete(relationship)
    db.query(GameInvitationModel).filter(
        GameInvitationModel.status == "pending",
        or_(
            (GameInvitationModel.sender_id == profile.id) & (GameInvitationModel.recipient_id == player_id),
            (GameInvitationModel.sender_id == player_id) & (GameInvitationModel.recipient_id == profile.id),
        ),
    ).update({"status": "cancelled", "active_key": None}, synchronize_session=False)
    db.commit()
    await presence_hub.broadcast_presence(profile.id, db)
    await presence_hub.broadcast_presence(player_id, db)
    return {"success": True}


@router.post("/api/social/blocks/{player_id}")
def block_player(
    player_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    if profile.id == player_id:
        raise HTTPException(status_code=400, detail="You cannot block yourself")
    target = _active_profile(db, player_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Player not found")
    existing = db.query(BlockedPlayerModel).filter(
        BlockedPlayerModel.blocker_id == profile.id,
        BlockedPlayerModel.blocked_id == target.id,
    ).first()
    if existing is None:
        db.add(BlockedPlayerModel(blocker_id=profile.id, blocked_id=target.id))
    relationship = _friendship(db, profile.id, target.id)
    if relationship is not None:
        db.delete(relationship)
    for friend_request in db.query(FriendRequestModel).filter(
        FriendRequestModel.pair_key == _pair_key(profile.id, target.id),
        FriendRequestModel.status == "pending",
    ).all():
        friend_request.status = "cancelled"
        friend_request.updated_at = get_utc_now()
    db.query(GameInvitationModel).filter(
        GameInvitationModel.status == "pending",
        or_(
            (GameInvitationModel.sender_id == profile.id) & (GameInvitationModel.recipient_id == target.id),
            (GameInvitationModel.sender_id == target.id) & (GameInvitationModel.recipient_id == profile.id),
        ),
    ).update({"status": "cancelled", "active_key": None}, synchronize_session=False)
    db.commit()
    return {"success": True}


@router.delete("/api/social/blocks/{player_id}")
def unblock_player(
    player_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    blocked = db.query(BlockedPlayerModel).filter(
        BlockedPlayerModel.blocker_id == profile.id,
        BlockedPlayerModel.blocked_id == player_id,
    ).first()
    if blocked is None:
        raise HTTPException(status_code=404, detail="Blocked player not found")
    db.delete(blocked)
    db.commit()
    return {"success": True}


@router.post("/api/social/reports")
def report_player(
    body: ReportInput,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    _apply_rate_limit(profile.id, "report")
    if profile.id == body.player_id:
        raise HTTPException(status_code=400, detail="You cannot report yourself")
    if _active_profile(db, body.player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")
    db.add(PlayerReportModel(
        reporter_id=profile.id,
        reported_id=body.player_id,
        category=body.category,
        details=body.details,
    ))
    db.commit()
    return {"success": True}


@router.post("/api/social/conversations/{player_id}")
def open_conversation(
    player_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    other = _active_profile(db, player_id)
    if other is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if not _friendship(db, profile.id, other.id) or _blocked(db, profile.id, other.id):
        raise HTTPException(status_code=403, detail="You can message friends only")
    conversation = _conversation_for(db, profile.id, other.id)
    return {"id": conversation.id, "player": _profile_summary(other)}


@router.get("/api/social/conversations/{conversation_id}/messages")
def read_conversation(
    conversation_id: str,
    limit: int = 50,
    before_id: Optional[int] = None,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    conversation, _other_id = _accessible_conversation(db, conversation_id, profile.id)
    limit = min(max(limit, 1), 100)
    query = db.query(PrivateMessageModel).filter(
        PrivateMessageModel.conversation_id == conversation.id
    )
    if before_id is not None:
        query = query.filter(PrivateMessageModel.id < before_id)
    messages = query.order_by(
        PrivateMessageModel.created_at.desc(), PrivateMessageModel.id.desc()
    ).limit(limit).all()
    now = get_utc_now()
    for message in messages:
        if message.recipient_id == profile.id and message.delivered_at is None:
            message.delivered_at = now
    db.commit()
    messages.reverse()
    return {"messages": [_message_payload(db, message, profile.id) for message in messages]}


@router.post("/api/social/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: MessageInput,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    _apply_rate_limit(profile.id, "message")
    conversation, recipient_id = _accessible_conversation(db, conversation_id, profile.id)
    message = PrivateMessageModel(
        conversation_id=conversation.id,
        sender_id=profile.id,
        recipient_id=recipient_id,
        content=body.content,
    )
    db.add(message)
    db.flush()
    notification = _notify(
        db, recipient_id, profile.id, "new_message",
        f"message:{message.id}",
        {
            "conversation_id": conversation.id,
            "message_id": message.id,
            "preview": body.content[:120],
        },
    )
    db.commit()
    delivered = await presence_hub.send(recipient_id, {
        "type": "MESSAGE",
        "conversation_id": conversation.id,
        "message": _message_payload(db, message, recipient_id),
    })
    if delivered:
        message.delivered_at = get_utc_now()
        db.commit()
    payload = _message_payload(db, message, profile.id)
    await presence_hub.publish_notification(db, notification)
    return payload


@router.post("/api/social/conversations/{conversation_id}/read")
def mark_conversation_read(
    conversation_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    conversation, _other_id = _accessible_conversation(db, conversation_id, profile.id)
    now = get_utc_now()
    db.query(PrivateMessageModel).filter(
        PrivateMessageModel.conversation_id == conversation.id,
        PrivateMessageModel.recipient_id == profile.id,
        PrivateMessageModel.read_at.is_(None),
    ).update({"read_at": now, "delivered_at": now}, synchronize_session=False)
    unread_notifications = db.query(SocialNotificationModel).filter(
        SocialNotificationModel.recipient_id == profile.id,
        SocialNotificationModel.notification_type == "new_message",
        SocialNotificationModel.read_at.is_(None),
    ).all()
    for notification in unread_notifications:
        try:
            payload = json.loads(notification.payload_json or "{}")
        except (TypeError, json.JSONDecodeError):
            logger.warning("Stored social notification %s has invalid JSON", notification.id)
            payload = {}
        if payload.get("conversation_id") == conversation.id:
            notification.read_at = now
    db.commit()
    return {"success": True}


@router.post("/api/social/invitations")
async def send_invitation(
    body: InvitationInput,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    _apply_rate_limit(profile.id, "invitation")
    recipient = _active_profile(db, body.player_id)
    if recipient is None:
        raise HTTPException(status_code=404, detail="Player not found")
    if profile.id == recipient.id:
        raise HTTPException(status_code=400, detail="You cannot invite yourself")
    if not _friendship(db, profile.id, recipient.id):
        raise HTTPException(status_code=403, detail="You can invite friends only")
    if _blocked(db, profile.id, recipient.id):
        raise HTTPException(status_code=403, detail="A block prevents this invitation")
    now = get_utc_now()
    pending = db.query(GameInvitationModel).filter(
        GameInvitationModel.sender_id == profile.id,
        GameInvitationModel.recipient_id == recipient.id,
        GameInvitationModel.game_mode == body.game_mode,
        GameInvitationModel.status == "pending",
    ).first()
    if pending:
        if (_utc(pending.expires_at) or now) > now:
            raise HTTPException(status_code=409, detail="An invitation is already pending")
        pending.status = "expired"
        pending.active_key = None
        db.flush()
    invitation = GameInvitationModel(
        id=str(uuid.uuid4()),
        sender_id=profile.id,
        recipient_id=recipient.id,
        game_mode=body.game_mode,
        status="pending",
        active_key=f"{profile.id}:{recipient.id}:{body.game_mode}",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    db.add(invitation)
    notification = _notify(
        db, recipient.id, profile.id, "game_invitation",
        f"game-invitation:{invitation.id}",
        {"invitation_id": invitation.id, "game_mode": body.game_mode},
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="An invitation is already pending")
    await presence_hub.publish_notification(db, notification)
    return {"success": True, "invitation_id": invitation.id}


@router.post("/api/social/invitations/{invitation_id}/accept")
async def accept_invitation(
    invitation_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    invitation = db.query(GameInvitationModel).filter(
        GameInvitationModel.id == invitation_id,
        GameInvitationModel.recipient_id == profile.id,
        GameInvitationModel.status == "pending",
    ).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    sender = _active_profile(db, invitation.sender_id)
    if sender is None or not _friendship(db, sender.id, profile.id) or _blocked(db, sender.id, profile.id):
        invitation.status = "cancelled"
        invitation.active_key = None
        db.commit()
        raise HTTPException(status_code=403, detail="This invitation is no longer available")
    now = get_utc_now()
    if (_utc(invitation.expires_at) or now) <= now:
        invitation.status = "expired"
        invitation.active_key = None
        db.commit()
        raise HTTPException(status_code=410, detail="This invitation has expired")
    launch = _create_invitation_room(db, invitation, sender, profile)
    if invitation.game_mode == "four_player":
        from app.db import RoomModel
        room = db.query(RoomModel).filter(RoomModel.room_code == launch["room_code"]).first()
        if room is None or room.status != "WAITING":
            raise HTTPException(status_code=409, detail="Four-Player room is not accepting players")
        players = json.loads(room.players_json or "{}")
        if len(players) > 4 or launch["player_role"] not in (1, 2, 3, 4):
            raise HTTPException(status_code=409, detail="Four-Player room capacity is unavailable")
    else:
        from app.db import ClassicRoomModel
        room = db.query(ClassicRoomModel).filter(ClassicRoomModel.room_code == launch["room_code"]).first()
        if room is None or room.status != "WAITING" or room.mode != "online":
            raise HTTPException(status_code=409, detail="Classic room is not available")
        players = json.loads(room.players_json or "{}")
        if len(players) != 2:
            raise HTTPException(status_code=409, detail="Classic room capacity is unavailable")

    invitation.status = "accepted"
    invitation.active_key = None
    invitation.room_code = launch["room_code"]
    invitation.recipient_player_id = launch["player_id"]
    notification = _notify(
        db, sender.id, profile.id, "invitation_accepted",
        f"invitation-accepted:{invitation.id}",
        {
            "invitation_id": invitation.id,
            "game_mode": invitation.game_mode,
            "room_code": launch["room_code"],
            "player_id": invitation.sender_player_id,
            "player_role": 1 if invitation.game_mode == "four_player" else None,
            "your_side": "white" if invitation.game_mode == "classic" else None,
        },
    )
    db.commit()
    await presence_hub.publish_notification(db, notification)
    return {"success": True, "launch": launch}


@router.post("/api/social/invitations/{invitation_id}/reject")
async def reject_invitation(
    invitation_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    invitation = db.query(GameInvitationModel).filter(
        GameInvitationModel.id == invitation_id,
        GameInvitationModel.recipient_id == profile.id,
        GameInvitationModel.status == "pending",
    ).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    invitation.status = "rejected"
    invitation.active_key = None
    sender = _active_profile(db, invitation.sender_id)
    notification = _notify(
        db, invitation.sender_id, profile.id, "invitation_rejected",
        f"invitation-rejected:{invitation.id}",
        {"invitation_id": invitation.id},
    )
    db.commit()
    if sender:
        await presence_hub.publish_notification(db, notification)
    return {"success": True}


@router.delete("/api/social/invitations/{invitation_id}")
def cancel_invitation(
    invitation_id: str,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    invitation = db.query(GameInvitationModel).filter(
        GameInvitationModel.id == invitation_id,
        GameInvitationModel.sender_id == profile.id,
        GameInvitationModel.status == "pending",
    ).first()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Pending invitation not found")
    invitation.status = "cancelled"
    invitation.active_key = None
    db.commit()
    return {"success": True}


@router.post("/api/social/notifications/read")
def mark_notifications_read(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    profile = _authorized_profile(authorization, db)
    db.query(SocialNotificationModel).filter(
        SocialNotificationModel.recipient_id == profile.id,
        SocialNotificationModel.read_at.is_(None),
    ).update({"read_at": get_utc_now()}, synchronize_session=False)
    db.commit()
    return {"success": True}


@router.websocket("/ws/social")
async def social_websocket(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    profile: Optional[PlayerProfileModel] = None
    try:
        raw_auth = await asyncio.wait_for(websocket.receive_text(), timeout=5)
        if len(raw_auth) > 2048:
            raise ValueError("Authentication frame is too large")
        auth_payload = json.loads(raw_auth)
        if not isinstance(auth_payload, dict) or auth_payload.get("type") != "AUTH":
            raise ValueError("Authentication frame is required")
        token = auth_payload.get("token")
        if not isinstance(token, str) or not token or len(token) > 160:
            raise ValueError("Invalid profile credential")
        profile = profile_from_authorization(f"Bearer {token}", db)
        if profile is None:
            raise ValueError("Invalid profile credential")
    except (asyncio.TimeoutError, json.JSONDecodeError, ValueError, WebSocketDisconnect):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await presence_hub.connect(profile.id, websocket, db)
    await websocket.send_json({
        "type": "SOCIAL_READY",
        "player_id": profile.id,
        "status": presence_hub.status(profile.id),
    })
    attempts: deque[float] = deque()
    last_announced_status = presence_hub.status(profile.id)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
            except asyncio.TimeoutError:
                current_status = presence_hub.status(profile.id)
                if current_status != last_announced_status:
                    await presence_hub.broadcast_presence(profile.id, db)
                    last_announced_status = current_status
                continue
            if len(raw) > 2048:
                await websocket.send_json({"type": "ERROR", "message": "Frame is too large"})
                continue
            now = time.monotonic()
            while attempts and now - attempts[0] > 10:
                attempts.popleft()
            if len(attempts) >= 30:
                await websocket.send_json({"type": "ERROR", "message": "Presence rate limit exceeded"})
                continue
            attempts.append(now)
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "ERROR", "message": "Invalid frame"})
                continue
            if not isinstance(event, dict):
                await websocket.send_json({"type": "ERROR", "message": "Frame must be an object"})
                continue
            if event.get("type") == "PING":
                await presence_hub.heartbeat(profile.id, False, db)
                last_announced_status = presence_hub.status(profile.id)
                await websocket.send_json({"type": "PONG"})
            elif event.get("type") == "ACTIVITY":
                await presence_hub.heartbeat(profile.id, True, db)
                last_announced_status = presence_hub.status(profile.id)
            else:
                await websocket.send_json({"type": "ERROR", "message": "Unsupported social event"})
    except WebSocketDisconnect:
        pass
    finally:
        await presence_hub.disconnect(profile.id, websocket, db)
