import json
import secrets

import pytest
from fastapi.testclient import TestClient

from app.db import (
    ClassicRoomModel,
    GameInvitationModel,
    PlayerReportModel,
    PrivateMessageModel,
    RoomModel,
    SessionLocal,
    init_db,
)
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def setup_social_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def new_player(client):
    created = client.post("/api/profile", json={})
    assert created.status_code == 200
    data = created.json()
    username = f"Social{secrets.randbelow(900000) + 100000}"
    updated = client.patch(
        "/api/profile",
        headers={"Authorization": f"Bearer {data['access_token']}"},
        json={"username": username},
    )
    assert updated.status_code == 200
    data["profile"] = updated.json()
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    return data


def make_friends(client, first, second):
    request = client.post(
        "/api/social/requests",
        headers=first["headers"],
        json={"player_id": second["profile"]["id"]},
    )
    assert request.status_code == 200
    request_id = request.json()["request_id"]
    accepted = client.post(
        f"/api/social/requests/{request_id}/accept",
        headers=second["headers"],
    )
    assert accepted.status_code == 200
    return request_id


def test_friend_request_lifecycle_duplicates_removal_and_cancellation(client):
    alice, bob, cara = (new_player(client) for _ in range(3))

    self_request = client.post(
        "/api/social/requests",
        headers=alice["headers"],
        json={"player_id": alice["profile"]["id"]},
    )
    assert self_request.status_code == 400

    pending = client.post(
        "/api/social/requests",
        headers=alice["headers"],
        json={"player_id": bob["profile"]["id"]},
    )
    assert pending.status_code == 200
    request_id = pending.json()["request_id"]
    duplicate = client.post(
        "/api/social/requests",
        headers=alice["headers"],
        json={"player_id": bob["profile"]["id"]},
    )
    assert duplicate.status_code == 409
    searched = client.get(
        "/api/social/players",
        headers=alice["headers"],
        params={"q": bob["profile"]["username"].lower()},
    )
    assert any(item["id"] == bob["profile"]["id"] for item in searched.json())
    inbox = client.get("/api/social/dashboard", headers=bob["headers"]).json()
    assert inbox["incoming_requests"][0]["id"] == request_id
    assert sum(item["type"] == "friend_request" for item in inbox["notifications"]) == 1
    outgoing_view = client.get("/api/social/dashboard", headers=alice["headers"]).json()["outgoing_requests"][0]
    assert outgoing_view["id"] == request_id
    assert outgoing_view["player"]["id"] == bob["profile"]["id"]

    accepted = client.post(
        f"/api/social/requests/{request_id}/accept",
        headers=bob["headers"],
    )
    assert accepted.status_code == 200
    assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"][0]["id"] == bob["profile"]["id"]
    assert client.post(
        "/api/social/requests",
        headers=alice["headers"],
        json={"player_id": bob["profile"]["id"]},
    ).status_code == 409

    removed = client.delete(
        f"/api/social/friends/{bob['profile']['id']}",
        headers=alice["headers"],
    )
    assert removed.status_code == 200
    assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"] == []

    outgoing = client.post(
        "/api/social/requests",
        headers=alice["headers"],
        json={"player_id": cara["profile"]["id"]},
    )
    assert outgoing.status_code == 200
    assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["outgoing_requests"][0]["player"]["id"] == cara["profile"]["id"]
    assert client.delete(
        f"/api/social/requests/{outgoing.json()['request_id']}",
        headers=alice["headers"],
    ).status_code == 200

    rejected = client.post(
        "/api/social/requests",
        headers=bob["headers"],
        json={"player_id": cara["profile"]["id"]},
    )
    assert rejected.status_code == 200
    assert client.post(
        f"/api/social/requests/{rejected.json()['request_id']}/reject",
        headers=cara["headers"],
    ).status_code == 200
    assert client.get("/api/social/dashboard", headers=cara["headers"]).json()["incoming_requests"] == []


def test_private_chat_history_delivery_authorization_block_and_report(client):
    alice, bob, outsider = (new_player(client) for _ in range(3))
    make_friends(client, alice, bob)

    conversation = client.post(
        f"/api/social/conversations/{bob['profile']['id']}",
        headers=alice["headers"],
    ).json()
    conversation_id = conversation["id"]
    message = client.post(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=alice["headers"],
        json={"content": "Good game 🙂 <script>"},
    )
    assert message.status_code == 200
    assert message.json()["content"] == "Good game 🙂 <script>"
    assert message.json()["status"] == "sent"

    forbidden = client.get(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=outsider["headers"],
    )
    assert forbidden.status_code == 404
    assert client.get(f"/api/social/conversations/{conversation_id}/messages").status_code == 401

    history = client.get(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=bob["headers"],
    )
    assert history.status_code == 200
    assert history.json()["messages"][0]["content"] == "Good game 🙂 <script>"
    delivered = client.get(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=alice["headers"],
    )
    assert delivered.json()["messages"][0]["status"] == "delivered"
    assert client.post(
        f"/api/social/conversations/{conversation_id}/read",
        headers=bob["headers"],
    ).status_code == 200
    read_status = client.get(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=alice["headers"],
    )
    assert read_status.json()["messages"][0]["status"] == "read"

    assert client.post(
        f"/api/social/blocks/{bob['profile']['id']}",
        headers=alice["headers"],
    ).status_code == 200
    search_after_block = client.get(
        "/api/social/players",
        headers=alice["headers"],
        params={"q": bob["profile"]["username"]},
    )
    assert all(item["id"] != bob["profile"]["id"] for item in search_after_block.json())
    assert client.post(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=bob["headers"],
        json={"content": "blocked"},
    ).status_code == 403
    assert client.get(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=bob["headers"],
    ).status_code == 403
    assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["blocked_players"][0]["id"] == bob["profile"]["id"]
    assert client.delete(
        f"/api/social/blocks/{bob['profile']['id']}",
        headers=alice["headers"],
    ).status_code == 200
    assert client.post(
        f"/api/social/conversations/{conversation_id}/messages",
        headers=alice["headers"],
        json={"content": " \n "},
    ).status_code == 422
    assert client.post(
        f"/api/social/reports",
        headers=alice["headers"],
        json={"player_id": outsider["profile"]["id"], "category": "spam", "details": "Report test"},
    ).status_code == 200

    with SessionLocal() as db:
        stored = db.query(PrivateMessageModel).filter(
            PrivateMessageModel.conversation_id == conversation_id
        ).all()
        assert len(stored) == 1
        reports = db.query(PlayerReportModel).filter(
            PlayerReportModel.reporter_id == alice["profile"]["id"]
        ).count()
        assert reports == 1


def test_invitation_lifecycle_and_room_mode_capacity(client):
    alice, bob = new_player(client), new_player(client)
    make_friends(client, alice, bob)

    invitation = client.post(
        "/api/social/invitations",
        headers=alice["headers"],
        json={"player_id": bob["profile"]["id"], "game_mode": "classic"},
    )
    assert invitation.status_code == 200
    invite_id = invitation.json()["invitation_id"]
    assert client.post(
        "/api/social/invitations",
        headers=alice["headers"],
        json={"player_id": bob["profile"]["id"], "game_mode": "classic"},
    ).status_code == 409
    assert client.get("/api/social/dashboard", headers=bob["headers"]).json()["invitations"][0]["id"] == invite_id
    assert client.post(
        f"/api/social/invitations/{invite_id}/reject",
        headers=bob["headers"],
    ).status_code == 200
    with SessionLocal() as db:
        saved = db.query(GameInvitationModel).filter(GameInvitationModel.id == invite_id).one()
        assert saved.status == "rejected"

    invitation = client.post(
        "/api/social/invitations",
        headers=alice["headers"],
        json={"player_id": bob["profile"]["id"], "game_mode": "four_player"},
    )
    accepted = client.post(
        f"/api/social/invitations/{invitation.json()['invitation_id']}/accept",
        headers=bob["headers"],
    )
    assert accepted.status_code == 200
    launch = accepted.json()["launch"]
    assert launch["game_mode"] == "four_player"
    with SessionLocal() as db:
        room = db.query(RoomModel).filter(RoomModel.room_code == launch["room_code"]).one()
        assert json.loads(room.settings_json)["game_mode"] == "four_player"
        assert len(json.loads(room.players_json)) == 2
        saved = db.query(GameInvitationModel).filter(
            GameInvitationModel.id == invitation.json()["invitation_id"]
        ).one()
        assert saved.status == "accepted"
        assert saved.room_code == launch["room_code"]
    with client.websocket_connect(f"/ws/{launch['room_code']}") as game_socket:
        game_socket.send_json({"type": "AUTH", "player_id": launch["player_id"]})
        sync = game_socket.receive_json()
        assert sync["type"] == "SYNC_STATE"
        assert sync["your_role"] == launch["player_role"] == 2
        assert sync["settings"]["game_mode"] == "four_player"
        game_socket.receive_json()
    inviter_notification = client.get(
        "/api/social/dashboard", headers=alice["headers"]
    ).json()["notifications"]
    accepted_notification = next(item for item in inviter_notification if item["type"] == "invitation_accepted")
    assert accepted_notification["payload"]["player_id"] == saved.sender_player_id
    assert accepted_notification["payload"]["player_id"] != launch["player_id"]

    classic_invite = client.post(
        "/api/social/invitations",
        headers=alice["headers"],
        json={"player_id": bob["profile"]["id"], "game_mode": "classic"},
    )
    classic_accept = client.post(
        f"/api/social/invitations/{classic_invite.json()['invitation_id']}/accept",
        headers=bob["headers"],
    )
    assert classic_accept.status_code == 200
    classic_launch = classic_accept.json()["launch"]
    assert classic_launch["game_mode"] == "classic"
    assert classic_launch["status"] == "WAITING"
    assert classic_launch["your_side"] == "black"
    with SessionLocal() as db:
        room = db.query(ClassicRoomModel).filter(
            ClassicRoomModel.room_code == classic_launch["room_code"]
        ).one()
        assert room.mode == "online"
        assert room.status == "WAITING"
        assert room.started_at is None
        assert len(json.loads(room.players_json)) == 2


def test_social_presence_notifications_and_disconnect_reconnect(client):
    alice, bob = new_player(client), new_player(client)
    make_friends(client, alice, bob)

    from app.social import presence_hub

    with client.websocket_connect("/ws/social") as socket:
        socket.send_json({"type": "AUTH", "token": bob["access_token"]})
        assert socket.receive_json()["type"] == "SOCIAL_READY"
        assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"][0]["status"] == "online"
        socket.send_json({"type": "PING"})
        assert socket.receive_json()["type"] == "PONG"
        presence_hub.activity[bob["profile"]["id"]] -= 181
        assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"][0]["status"] == "away"
        socket.send_json({"type": "ACTIVITY"})
        assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"][0]["status"] == "online"
        socket.send_json({"type": "PRESENCE", "status": "online"})
        assert socket.receive_json()["type"] == "ERROR"

        invitation = client.post(
            "/api/social/invitations",
            headers=alice["headers"],
            json={"player_id": bob["profile"]["id"], "game_mode": "four_player"},
        )
        assert invitation.status_code == 200
        delivered = socket.receive_json()
        assert delivered["type"] == "NOTIFICATION"
        assert delivered["notification"]["type"] == "game_invitation"
        socket.send_json({"type": "ACTIVITY"})

        classic_invitation = client.post(
            "/api/social/invitations",
            headers=alice["headers"],
            json={"player_id": bob["profile"]["id"], "game_mode": "classic"},
        ).json()
        assert socket.receive_json()["notification"]["type"] == "game_invitation"
        classic_launch = client.post(
            f"/api/social/invitations/{classic_invitation['invitation_id']}/accept",
            headers=bob["headers"],
        ).json()["launch"]
        with SessionLocal() as db:
            classic_room = db.query(ClassicRoomModel).filter(
                ClassicRoomModel.room_code == classic_launch["room_code"]
            ).one()
            host_player_id = json.loads(classic_room.players_json)["white"]["player_id"]
        with client.websocket_connect(f"/ws/classic/{classic_launch['room_code']}") as game_socket:
            game_socket.send_json({"type": "AUTH", "player_id": classic_launch["player_id"]})
            assert game_socket.receive_json()["type"] == "SYNC_STATE"
            with client.websocket_connect(f"/ws/classic/{classic_launch['room_code']}") as host_socket:
                host_socket.send_json({"type": "AUTH", "player_id": host_player_id})
                assert host_socket.receive_json()["type"] == "SYNC_STATE"
                assert host_socket.receive_json()["type"] == "PRESENCE_UPDATE"
                assert game_socket.receive_json()["type"] == "PRESENCE_UPDATE"
                assert game_socket.receive_json()["type"] == "PRESENCE_UPDATE"
                host_socket.send_json({"type": "START_GAME"})
                assert host_socket.receive_json()["event"] == "START_GAME"
                assert game_socket.receive_json()["event"] == "START_GAME"
                assert client.get(
                    "/api/social/dashboard", headers=alice["headers"]
                ).json()["friends"][0]["status"] == "playing"
        assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"][0]["status"] == "online"

    assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"][0]["status"] == "offline"
    with client.websocket_connect("/ws/social") as socket:
        socket.send_json({"type": "AUTH", "token": bob["access_token"]})
        assert socket.receive_json()["type"] == "SOCIAL_READY"
    assert client.get("/api/social/dashboard", headers=alice["headers"]).json()["friends"][0]["status"] == "offline"
