import pytest
from app.engine import (
    FourPlayerChessEngine, Move, Piece, is_valid_square,
    PLAYER_CYAN, PLAYER_MAGENTA, PLAYER_LIME, PLAYER_GOLD
)

def test_board_geometry_and_voids():
    engine = FourPlayerChessEngine()
    # Check 4 corner cutouts (3x3 each = 36 void squares)
    void_count = 0
    valid_count = 0
    for r in range(14):
        for c in range(14):
            if is_valid_square(r, c):
                valid_count += 1
            else:
                void_count += 1

    assert void_count == 36
    assert valid_count == 160
    assert not is_valid_square(0, 0)
    assert not is_valid_square(0, 2)
    assert not is_valid_square(2, 0)
    assert not is_valid_square(0, 13)
    assert not is_valid_square(13, 0)
    assert not is_valid_square(13, 13)
    assert is_valid_square(0, 3)
    assert is_valid_square(3, 0)
    assert is_valid_square(7, 7)

def test_initial_piece_setup():
    engine = FourPlayerChessEngine()
    # Each player should have 16 pieces: 1 King, 1 Queen, 2 Rooks, 2 Bishops, 2 Knights, 8 Pawns
    counts = {p: {} for p in range(1, 5)}
    for r in range(14):
        for c in range(14):
            piece = engine.get_piece(r, c)
            if piece:
                counts[piece.player][piece.type] = counts[piece.player].get(piece.type, 0) + 1

    for p in range(1, 5):
        assert counts[p]['K'] == 1
        assert counts[p]['Q'] == 1
        assert counts[p]['R'] == 2
        assert counts[p]['B'] == 2
        assert counts[p]['N'] == 2
        assert counts[p]['P'] == 8

    # Check King positions
    assert engine.find_king(PLAYER_CYAN) == (13, 7)
    assert engine.find_king(PLAYER_LIME) == (0, 7)
    assert engine.find_king(PLAYER_MAGENTA) == (7, 0)
    assert engine.find_king(PLAYER_GOLD) == (7, 13)

def test_pawn_forward_and_double_step():
    engine = FourPlayerChessEngine()
    # Cyan moves pawn up: (12, 6) -> (11, 6) or (10, 6)
    legal_moves = engine.get_legal_moves(PLAYER_CYAN)
    m1 = Move((12, 6), (11, 6))
    m2 = Move((12, 6), (10, 6))
    assert m1 in legal_moves
    assert m2 in legal_moves

    # Execute Cyan pawn 2 steps forward
    success, msg = engine.make_move(m2)
    assert success
    assert engine.get_piece(10, 6).type == 'P'
    assert engine.get_piece(10, 6).player == PLAYER_CYAN
    assert engine.get_piece(12, 6) is None

    # Next player must be Magenta (West)
    assert engine.current_turn == PLAYER_MAGENTA

    # Magenta moves pawn right: (6, 1) -> (6, 2) or (6, 3)
    m_mag = Move((6, 1), (6, 3))
    assert m_mag in engine.get_legal_moves(PLAYER_MAGENTA)
    success, _ = engine.make_move(m_mag)
    assert success
    assert engine.current_turn == PLAYER_LIME

    # Lime moves pawn down: (1, 6) -> (3, 6)
    m_lime = Move((1, 6), (3, 6))
    assert m_lime in engine.get_legal_moves(PLAYER_LIME)
    success, _ = engine.make_move(m_lime)
    assert success
    assert engine.current_turn == PLAYER_GOLD

    # Gold moves pawn left: (6, 12) -> (6, 10)
    m_gold = Move((6, 12), (6, 10))
    assert m_gold in engine.get_legal_moves(PLAYER_GOLD)
    success, _ = engine.make_move(m_gold)
    assert success

    # Back to Cyan
    assert engine.current_turn == PLAYER_CYAN

def test_knight_movement_over_pieces():
    engine = FourPlayerChessEngine()
    # Cyan knight at (13, 4) can jump over pawns to (11, 3) and (11, 5)
    legal = engine.get_legal_moves(PLAYER_CYAN)
    k_move1 = Move((13, 4), (11, 3))
    k_move2 = Move((13, 4), (11, 5))
    assert k_move1 in legal
    assert k_move2 in legal

def test_pawn_captures():
    engine = FourPlayerChessEngine()
    # Clear board and place Cyan pawn at (8, 6) and Lime piece at (7, 5)
    engine.board = [[None for _ in range(14)] for _ in range(14)]
    engine.board[13][7] = Piece('K', PLAYER_CYAN)
    engine.board[0][7] = Piece('K', PLAYER_LIME)
    engine.board[7][0] = Piece('K', PLAYER_MAGENTA)
    engine.board[7][13] = Piece('K', PLAYER_GOLD)

    engine.board[8][6] = Piece('P', PLAYER_CYAN)
    engine.board[7][5] = Piece('N', PLAYER_LIME)

    legal = engine.get_legal_moves(PLAYER_CYAN)
    capture_move = Move((8, 6), (7, 5))
    assert capture_move in legal

    success, _ = engine.make_move(capture_move)
    assert success
    assert engine.get_piece(7, 5).type == 'P'
    assert 'N' in engine.captured_pieces[PLAYER_CYAN]

def test_pawn_promotion():
    engine = FourPlayerChessEngine()
    engine.board = [[None for _ in range(14)] for _ in range(14)]
    engine.board[13][7] = Piece('K', PLAYER_CYAN)
    engine.board[0][7] = Piece('K', PLAYER_LIME)
    engine.board[7][0] = Piece('K', PLAYER_MAGENTA)
    engine.board[7][13] = Piece('K', PLAYER_GOLD)

    # Place Cyan pawn at row 6, advancing to row 5 (8th rank triggers promotion)
    engine.board[6][6] = Piece('P', PLAYER_CYAN)
    legal = engine.get_legal_moves(PLAYER_CYAN)

    promo_moves = [m for m in legal if m.from_sq == (6, 6) and m.to_sq == (5, 6)]
    assert len(promo_moves) == 4  # Q, R, B, N promotions
    promo_types = {m.promotion for m in promo_moves}
    assert promo_types == {'Q', 'R', 'B', 'N'}

    # Execute promotion to Queen
    q_move = Move((6, 6), (5, 6), promotion='Q')
    success, _ = engine.make_move(q_move)
    assert success
    promoted = engine.get_piece(5, 6)
    assert promoted.type == 'Q'
    assert promoted.player == PLAYER_CYAN

def test_check_and_pins():
    engine = FourPlayerChessEngine()
    engine.board = [[None for _ in range(14)] for _ in range(14)]
    engine.board[13][7] = Piece('K', PLAYER_CYAN)
    engine.board[0][7] = Piece('K', PLAYER_LIME)
    engine.board[7][0] = Piece('K', PLAYER_MAGENTA)
    engine.board[7][13] = Piece('K', PLAYER_GOLD)

    # Lime rook at (5, 7) attacks Cyan King at (13, 7)
    engine.board[5][7] = Piece('R', PLAYER_LIME)

    assert engine.is_in_check(PLAYER_CYAN)

    # Cyan has to escape check: move king, block with piece, or capture attacker
    legal = engine.get_legal_moves(PLAYER_CYAN)
    # Moving king to (13, 6) or (13, 8) escapes check
    assert Move((13, 7), (13, 6)) in legal
    assert Move((13, 7), (13, 8)) in legal
    # Moving king to (12, 7) is illegal (still on Rook ray)
    assert Move((13, 7), (12, 7)) not in legal

def test_elimination_and_last_player_standing():
    engine = FourPlayerChessEngine()
    engine.board = [[None for _ in range(14)] for _ in range(14)]
    engine.board[13][7] = Piece('K', PLAYER_CYAN)
    engine.board[0][7] = Piece('K', PLAYER_LIME)
    engine.board[7][0] = Piece('K', PLAYER_MAGENTA)
    engine.board[7][13] = Piece('K', PLAYER_GOLD)

    assert len(engine.active_players) == 4
    assert not engine.is_game_over

    # Resign Magenta
    engine.resign_player(PLAYER_MAGENTA)
    assert PLAYER_MAGENTA in engine.eliminated_players
    assert len(engine.active_players) == 3

    # Resign Lime
    engine.resign_player(PLAYER_LIME)
    assert len(engine.active_players) == 2

    # Resign Gold -> Cyan wins!
    engine.resign_player(PLAYER_GOLD)
    assert len(engine.active_players) == 1
    assert engine.is_game_over
    assert engine.winner == PLAYER_CYAN

def test_undo_move():
    engine = FourPlayerChessEngine()
    init_state = engine.get_state()

    m = Move((12, 6), (10, 6))
    engine.make_move(m)
    assert engine.current_turn == PLAYER_MAGENTA

    success, _ = engine.undo_move()
    assert success
    assert engine.current_turn == PLAYER_CYAN
    assert engine.get_piece(10, 6) is None
    assert engine.get_piece(12, 6).type == 'P'
