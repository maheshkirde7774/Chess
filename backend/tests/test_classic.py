import chess
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.classic import ClassicGame, classic_rooms
from app.db import init_db
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    init_db()


@pytest.fixture
def client():
    return TestClient(app)


def test_classic_starting_position_and_six_piece_movements():
    game = ClassicGame("unlimited", started=False)
    assert game.board.fen() == chess.STARTING_FEN
    assert game.board.legal_moves.count() == 20

    positions = [
        ("4k3/8/8/8/8/8/8/R3K3 w - - 0 1", "a1a8"),
        ("4k3/8/8/8/8/8/8/2B1K3 w - - 0 1", "c1h6"),
        ("4k3/8/8/8/8/8/8/3QK3 w - - 0 1", "d1d8"),
        ("4k3/8/8/8/8/8/8/4K3 w - - 0 1", "e1e2"),
        ("4k3/8/8/8/8/8/8/1N2K3 w - - 0 1", "b1c3"),
        ("4k3/8/8/8/8/8/3P4/4K3 w - - 0 1", "d2d4"),
    ]
    for fen, uci in positions:
        board = chess.Board(fen)
        assert chess.Move.from_uci(uci) in board.legal_moves


def test_illegal_move_check_and_checkmate():
    game = ClassicGame("unlimited", started=False)
    with pytest.raises(ValueError, match="Illegal"):
        game.play("e2", "e5", None)
    for source, target in [("f2", "f3"), ("e7", "e5"), ("g2", "g4"), ("d8", "h4")]:
        game.play(source, target, None)
    state = game.snapshot()
    assert state["in_check"] is True
    assert state["result"] == "0-1"
    assert state["termination"] == "checkmate"


def test_stalemate_and_insufficient_material():
    game = ClassicGame("unlimited", started=False)
    game.board = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert game.snapshot()["termination"] == "stalemate"

    game = ClassicGame("unlimited", started=False)
    game.board = chess.Board("8/8/8/8/8/8/4k3/4K3 w - - 0 1")
    assert game.snapshot()["result"] == "1/2-1/2"
    assert game.snapshot()["termination"] == "insufficient_material"


def test_castling_en_passant_and_promotion():
    castling_moves = [
        ("e1", "g1", chess.G1, chess.F1, "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"),
        ("e1", "c1", chess.C1, chess.D1, "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"),
        ("e8", "g8", chess.G8, chess.F8, "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1"),
        ("e8", "c8", chess.C8, chess.D8, "r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1"),
    ]
    for source, target, king_square, rook_square, fen in castling_moves:
        game = ClassicGame("unlimited", started=False)
        game.board = chess.Board(fen)
        game.play(source, target, None)
        assert game.board.piece_at(king_square).piece_type == chess.KING
        assert game.board.piece_at(rook_square).piece_type == chess.ROOK

    game = ClassicGame("unlimited", started=False)
    for source, target in [("e2", "e4"), ("a7", "a6"), ("e4", "e5"), ("d7", "d5")]:
        game.play(source, target, None)
    game.play("e5", "d6", None)
    assert game.board.piece_at(chess.D5) is None
    assert game.captured["white"] == ["p"]

    promotion_types = {
        "q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT,
    }
    for promotion, piece_type in promotion_types.items():
        game = ClassicGame("unlimited", started=False)
        game.board = chess.Board("7k/P7/8/8/8/8/8/7K w - - 0 1")
        game.play("a7", "a8", promotion)
        assert game.board.piece_at(chess.A8).piece_type == piece_type


def test_threefold_and_fifty_move_draws():
    game = ClassicGame("unlimited", started=False)
    cycle = [("g1", "f3"), ("g8", "f6"), ("f3", "g1"), ("f6", "g8")]
    for _ in range(2):
        for source, target in cycle:
            game.play(source, target, None)
    assert game.snapshot()["result"] is None
    assert game.snapshot()["can_claim_draw"] is True
    game.claim_draw()
    assert game.snapshot()["termination"] == "threefold_repetition"

    game = ClassicGame("unlimited", started=False)
    game.board = chess.Board("7k/8/8/8/8/8/8/R6K w - - 99 50")
    game.play("a1", "a2", None)
    assert game.snapshot()["result"] is None
    assert game.snapshot()["can_claim_draw"] is True
    game.claim_draw()
    assert game.snapshot()["termination"] == "fifty_moves"


def test_authoritative_clock_and_restart_clock_checkpoint(monkeypatch):
    import app.classic as classic_module

    now = [100.0]
    monkeypatch.setattr(classic_module.time, "time", lambda: now[0])
    game = ClassicGame("1+0", started=True)
    now[0] = 105.0
    saved = game.serialize()
    assert saved["clocks"]["white"] == 55.0

    restored = ClassicGame.restore(saved, "1+0")
    now[0] = 108.0
    assert restored.snapshot()["clocks"]["white"] == 52.0
    now[0] = 161.0
    assert restored.snapshot()["result"] == "0-1"
    assert restored.snapshot()["termination"] == "timeout"

    now[0] = 200.0
    increment_game = ClassicGame("15+10", started=True)
    now[0] = 205.0
    increment_game.play("e2", "e4", None)
    assert increment_game.snapshot()["clocks"]["white"] == 905.0
    assert increment_game.snapshot()["clocks"]["black"] == 900.0


def test_room_join_authorization_and_sqlite_persistence(client):
    created = client.post("/classic/rooms", json={
        "player_name": "Alice", "time_control": "5+0", "mode": "online",
    })
    assert created.status_code == 200
    white = created.json()
    assert white["game_state"]["fen"] == chess.STARTING_FEN
    code = white["room_code"]

    joined = client.post("/classic/rooms/join", json={"room_code": code, "player_name": "Bob"})
    assert joined.status_code == 200
    black = joined.json()
    assert black["your_side"] == "black"
    assert black["status"] == "WAITING"
    assert "player_id" not in joined.json()["players"]["white"]
    assert client.post("/classic/rooms/join", json={"room_code": code}).status_code == 400
    assert client.post(f"/classic/rooms/{code}/start", json={"player_id": black["player_id"]}).status_code == 403
    assert client.post(f"/classic/rooms/{code}/start", json={"player_id": white["player_id"]}).status_code == 200
    assert client.get(
        f"/classic/rooms/{code}", headers={"Authorization": "Bearer not-a-token"},
    ).status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/classic/{code}") as socket:
            socket.send_json({"type": "AUTH", "player_id": "not-a-token"})
            socket.receive_json()

    with client.websocket_connect(f"/ws/classic/{code}") as white_ws:
        white_ws.send_json({"type": "AUTH", "player_id": white["player_id"]})
        assert white_ws.receive_json()["type"] == "SYNC_STATE"
        white_ws.receive_json()  # Presence broadcast
        with client.websocket_connect(f"/ws/classic/{code}") as black_ws:
            black_ws.send_json({"type": "AUTH", "player_id": black["player_id"]})
            assert black_ws.receive_json()["type"] == "SYNC_STATE"
            black_ws.receive_json()  # Presence broadcast
            white_ws.receive_json()  # Black connected

            black_ws.send_json({"type": "MOVE", "from": "e7", "to": "e5"})
            assert black_ws.receive_json()["type"] == "ERROR"
            white_ws.send_json({"type": "MOVE", "from": "e2", "to": "e4"})
            white_state = white_ws.receive_json()
            black_state = black_ws.receive_json()
            assert white_state["type"] == black_state["type"] == "GAME_STATE"
            assert white_state["game_state"]["fen"] == black_state["game_state"]["fen"]
            assert white_state["game_state"]["moves"][0]["san"] == "e4"

    classic_rooms.pop(code)
    restored = client.get(
        f"/classic/rooms/{code}",
        headers={"Authorization": f"Bearer {white['player_id']}"},
    )
    assert restored.status_code == 200
    assert restored.json()["game_state"]["moves"][0]["uci"] == "e2e4"
    with client.websocket_connect(f"/ws/classic/{code}") as reconnected_ws:
        reconnected_ws.send_json({"type": "AUTH", "player_id": white["player_id"]})
        assert reconnected_ws.receive_json()["game_state"]["moves"][0]["uci"] == "e2e4"


def test_local_room_starts_immediately_and_rejects_join(client):
    created = client.post("/classic/rooms", json={"mode": "local", "time_control": "unlimited"})
    assert created.status_code == 200
    data = created.json()
    assert data["status"] == "PLAYING"
    assert client.post("/classic/rooms/join", json={"room_code": data["room_code"]}).status_code == 400


def test_public_classic_room_discovery_and_host_start(client):
    created = client.post("/classic/rooms", json={
        "player_name": "Host", "is_private": False, "time_control": "5+0",
    })
    host = created.json()
    public = client.get("/rooms").json()
    listed = next(room for room in public if room["room_code"] == host["room_code"])
    assert listed["settings"]["game_mode"] == "classic"
    assert listed["settings"]["max_players"] == 2
    assert "player_id" not in str(listed["players"])
    joined = client.post("/classic/rooms/join", json={
        "room_code": host["room_code"], "player_name": "Guest",
    }).json()
    assert joined["status"] == "WAITING"
    assert client.post(
        f"/classic/rooms/{host['room_code']}/start",
        json={"player_id": host["player_id"]},
    ).status_code == 200


def test_host_websocket_presence_does_not_start_waiting_room(client):
    created = client.post("/classic/rooms", json={"mode": "online"}).json()
    code = created["room_code"]
    with client.websocket_connect(f"/ws/classic/{code}") as host_ws:
        host_ws.send_json({"type": "AUTH", "player_id": created["player_id"]})
        assert host_ws.receive_json()["status"] == "WAITING"
        host_ws.receive_json()
        joined = client.post("/classic/rooms/join", json={"room_code": code})
        assert joined.status_code == 200
        assert host_ws.receive_json()["type"] == "PLAYER_JOINED"
