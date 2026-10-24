"""
Neon Four Chess - 4-Player Chess Engine
Cross-shaped 14x14 board with 4 armies:
- Player 1: Cyan (South / Bottom)
- Player 2: Magenta (West / Left)
- Player 3: Lime Green (North / Top)
- Player 4: Gold (East / Right)
"""

from typing import List, Dict, Optional, Tuple, Set, Any
import copy
import json

# Board Dimensions
BOARD_SIZE = 14

# Corner Cutouts (3x3 squares at each corner are out-of-bounds)
CUTOUTS = set()
for r in range(3):
    for c in range(3):
        CUTOUTS.add((r, c))          # Top-Left
        CUTOUTS.add((r, 13 - c))     # Top-Right
        CUTOUTS.add((13 - r, c))     # Bottom-Left
        CUTOUTS.add((13 - r, 13 - c))# Bottom-Right

def is_valid_square(r: int, c: int) -> bool:
    """Returns True if (r, c) is on the 14x14 cross-shaped board and not in a corner cutout."""
    if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
        return (r, c) not in CUTOUTS
    return False

# Player Constants
PLAYER_CYAN = 1      # South
PLAYER_MAGENTA = 2   # West
PLAYER_LIME = 3      # North
PLAYER_GOLD = 4      # East

PLAYER_NAMES = {
    PLAYER_CYAN: "Cyan (South)",
    PLAYER_MAGENTA: "Magenta (West)",
    PLAYER_LIME: "Lime (North)",
    PLAYER_GOLD: "Gold (East)"
}

PLAYER_COLORS = {
    PLAYER_CYAN: "#00f3ff",
    PLAYER_MAGENTA: "#ff007f",
    PLAYER_LIME: "#39ff14",
    PLAYER_GOLD: "#ffd700"
}

# Piece Types: 'P' (Pawn), 'N' (Knight), 'B' (Bishop), 'R' (Rook), 'Q' (Queen), 'K' (King)
PIECE_SYMBOLS = {'P', 'N', 'B', 'R', 'Q', 'K'}

class Piece:
    def __init__(self, piece_type: str, player: int, has_moved: bool = False, is_dormant: bool = False):
        self.type = piece_type.upper()
        self.player = player
        self.has_moved = has_moved
        self.is_dormant = is_dormant  # Pieces of eliminated players become dormant obstacles

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "player": self.player,
            "has_moved": self.has_moved,
            "is_dormant": self.is_dormant
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Piece":
        return cls(
            piece_type=data["type"],
            player=data["player"],
            has_moved=data.get("has_moved", False),
            is_dormant=data.get("is_dormant", False)
        )

    def __repr__(self) -> str:
        d = "*" if self.is_dormant else ""
        return f"{self.type}{self.player}{d}"


class Move:
    def __init__(self, from_sq: Tuple[int, int], to_sq: Tuple[int, int], promotion: Optional[str] = None):
        self.from_sq = from_sq
        self.to_sq = to_sq
        self.promotion = promotion.upper() if promotion else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from": [self.from_sq[0], self.from_sq[1]],
            "to": [self.to_sq[0], self.to_sq[1]],
            "promotion": self.promotion
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Move":
        from_sq = tuple(data["from"])
        to_sq = tuple(data["to"])
        return cls(from_sq, to_sq, data.get("promotion"))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Move):
            return False
        return (self.from_sq == other.from_sq and
                self.to_sq == other.to_sq and
                self.promotion == other.promotion)

    def __repr__(self) -> str:
        promo = f"={self.promotion}" if self.promotion else ""
        return f"{self.from_sq}->{self.to_sq}{promo}"


class FourPlayerChessEngine:
    def __init__(self):
        self.board: List[List[Optional[Piece]]] = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.current_turn: int = PLAYER_CYAN
        self.active_players: List[int] = [PLAYER_CYAN, PLAYER_MAGENTA, PLAYER_LIME, PLAYER_GOLD]
        self.eliminated_players: List[int] = []
        self.winner: Optional[int] = None
        self.is_game_over: bool = False
        self.move_history: List[Dict[str, Any]] = []
        self.captured_pieces: Dict[int, List[str]] = {p: [] for p in range(1, 5)}
        self.halfmove_clock: int = 0  # For 50-move rule
        self.turn_number: int = 1
        self.last_move: Optional[Move] = None

        self.setup_initial_board()

    def setup_initial_board(self) -> None:
        """Sets up the initial 14x14 board with the 4 symmetric armies."""
        self.board = [[None for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]

        # --- Player 1: Cyan (South / Bottom) ---
        # Back rank: row 13, cols 3..10
        # Order: R, N, B, Q, K, B, N, R
        p1_back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        for idx, p_type in enumerate(p1_back):
            self.board[13][3 + idx] = Piece(p_type, PLAYER_CYAN)
        # Pawns: row 12, cols 3..10
        for c in range(3, 11):
            self.board[12][c] = Piece('P', PLAYER_CYAN)

        # --- Player 3: Lime Green (North / Top) ---
        # Back rank: row 0, cols 3..10
        # Facing South: symmetric to Cyan (Q on col 6, K on col 7 or facing Queen to Queen)
        # From Lime's perspective, left to right: R, N, B, Q, K, B, N, R
        # Looking from top down: Col 10 is Lime's right, Col 3 is Lime's left.
        # Let's align King and Queen opposite:
        # Col 6: King, Col 7: Queen (so Cyan Queen on col 6 faces Lime King on col 6, or Queen opposite Queen)
        # Standard: Cyan Queen is at (13, 6). Lime Queen at (0, 6) or (0, 7)?
        # Let's place Lime Queen at (0, 6) and King at (0, 7) for direct symmetrical face-off.
        p3_back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        for idx, p_type in enumerate(p3_back):
            self.board[0][3 + idx] = Piece(p_type, PLAYER_LIME)
        # Pawns: row 1, cols 3..10
        for c in range(3, 11):
            self.board[1][c] = Piece('P', PLAYER_LIME)

        # --- Player 2: Magenta (West / Left) ---
        # Back rank: col 0, rows 3..10
        # Pawns: col 1, rows 3..10
        # Order: R, N, B, Q, K, B, N, R along rows 3..10
        p2_back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        for idx, p_type in enumerate(p2_back):
            self.board[3 + idx][0] = Piece(p_type, PLAYER_MAGENTA)
        for r in range(3, 11):
            self.board[r][1] = Piece('P', PLAYER_MAGENTA)

        # --- Player 4: Gold (East / Right) ---
        # Back rank: col 13, rows 3..10
        # Pawns: col 12, rows 3..10
        p4_back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R']
        for idx, p_type in enumerate(p4_back):
            self.board[3 + idx][13] = Piece(p_type, PLAYER_GOLD)
        for r in range(3, 11):
            self.board[r][12] = Piece('P', PLAYER_GOLD)

    def get_piece(self, r: int, c: int) -> Optional[Piece]:
        if is_valid_square(r, c):
            return self.board[r][c]
        return None

    def find_king(self, player: int) -> Optional[Tuple[int, int]]:
        """Finds the current coordinate of the specified player's King."""
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                p = self.board[r][c]
                if p and p.player == player and p.type == 'K' and not p.is_dormant:
                    return (r, c)
        return None

    def is_square_attacked(self, target_r: int, target_c: int, by_player: Optional[int] = None) -> bool:
        """
        Returns True if (target_r, target_c) is under attack by any active piece
        belonging to by_player (or any opponent if by_player is None).
        """
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                piece = self.board[r][c]
                if not piece or piece.is_dormant or piece.player in self.eliminated_players:
                    continue
                if by_player is not None and piece.player != by_player:
                    continue

                # Check if this piece can attack target_r, target_c
                if self._can_piece_attack(r, c, piece, target_r, target_c):
                    return True
        return False

    def _can_piece_attack(self, from_r: int, from_c: int, piece: Piece, to_r: int, to_c: int) -> bool:
        """Helper to determine if a piece at (from_r, from_c) threatens (to_r, to_c)."""
        dr = to_r - from_r
        dc = to_c - from_c

        if piece.type == 'P':
            # Pawns attack diagonally forward based on player direction
            if piece.player == PLAYER_CYAN:      # Moves up (-1, 0) -> attacks (-1, -1) and (-1, 1)
                return dr == -1 and abs(dc) == 1
            elif piece.player == PLAYER_MAGENTA: # Moves right (0, 1) -> attacks (-1, 1) and (1, 1)
                return dc == 1 and abs(dr) == 1
            elif piece.player == PLAYER_LIME:    # Moves down (1, 0) -> attacks (1, -1) and (1, 1)
                return dr == 1 and abs(dc) == 1
            elif piece.player == PLAYER_GOLD:    # Moves left (0, -1) -> attacks (-1, -1) and (1, -1)
                return dc == -1 and abs(dr) == 1
            return False

        elif piece.type == 'N':
            return (abs(dr) == 1 and abs(dc) == 2) or (abs(dr) == 2 and abs(dc) == 1)

        elif piece.type == 'B':
            if abs(dr) == abs(dc) and dr != 0:
                step_r = 1 if dr > 0 else -1
                step_c = 1 if dc > 0 else -1
                cur_r, cur_c = from_r + step_r, from_c + step_c
                while (cur_r, cur_c) != (to_r, to_c):
                    if not is_valid_square(cur_r, cur_c) or self.board[cur_r][cur_c] is not None:
                        return False
                    cur_r += step_r
                    cur_c += step_c
                return True
            return False

        elif piece.type == 'R':
            if (dr == 0 and dc != 0) or (dc == 0 and dr != 0):
                step_r = (1 if dr > 0 else -1) if dr != 0 else 0
                step_c = (1 if dc > 0 else -1) if dc != 0 else 0
                cur_r, cur_c = from_r + step_r, from_c + step_c
                while (cur_r, cur_c) != (to_r, to_c):
                    if not is_valid_square(cur_r, cur_c) or self.board[cur_r][cur_c] is not None:
                        return False
                    cur_r += step_r
                    cur_c += step_c
                return True
            return False

        elif piece.type == 'Q':
            # Combination of Bishop and Rook
            if abs(dr) == abs(dc) and dr != 0:
                step_r = 1 if dr > 0 else -1
                step_c = 1 if dc > 0 else -1
                cur_r, cur_c = from_r + step_r, from_c + step_c
                while (cur_r, cur_c) != (to_r, to_c):
                    if not is_valid_square(cur_r, cur_c) or self.board[cur_r][cur_c] is not None:
                        return False
                    cur_r += step_r
                    cur_c += step_c
                return True
            elif (dr == 0 and dc != 0) or (dc == 0 and dr != 0):
                step_r = (1 if dr > 0 else -1) if dr != 0 else 0
                step_c = (1 if dc > 0 else -1) if dc != 0 else 0
                cur_r, cur_c = from_r + step_r, from_c + step_c
                while (cur_r, cur_c) != (to_r, to_c):
                    if not is_valid_square(cur_r, cur_c) or self.board[cur_r][cur_c] is not None:
                        return False
                    cur_r += step_r
                    cur_c += step_c
                return True
            return False

        elif piece.type == 'K':
            return max(abs(dr), abs(dc)) == 1

        return False

    def is_in_check(self, player: int) -> bool:
        """Returns True if the specified player's King is in check by any active opponent."""
        king_pos = self.find_king(player)
        if not king_pos:
            return False
        # Check against all other active players
        for opp in self.active_players:
            if opp != player:
                if self.is_square_attacked(king_pos[0], king_pos[1], by_player=opp):
                    return True
        return False

    def get_pseudo_legal_moves(self, r: int, c: int) -> List[Move]:
        """Generates all pseudo-legal moves for the piece at (r, c) without filtering self-checks."""
        piece = self.board[r][c]
        if not piece or piece.is_dormant:
            return []

        moves: List[Move] = []
        player = piece.player

        if piece.type == 'P':
            moves.extend(self._get_pawn_moves(r, c, piece))
        elif piece.type == 'N':
            knight_offsets = [
                (-2, -1), (-2, 1), (-1, -2), (-1, 2),
                (1, -2), (1, 2), (2, -1), (2, 1)
            ]
            for dr, dc in knight_offsets:
                nr, nc = r + dr, c + dc
                if is_valid_square(nr, nc):
                    target = self.board[nr][nc]
                    if target is None or target.player != player:
                        moves.append(Move((r, c), (nr, nc)))
        elif piece.type == 'B':
            moves.extend(self._get_ray_moves(r, c, player, [(-1, -1), (-1, 1), (1, -1), (1, 1)]))
        elif piece.type == 'R':
            moves.extend(self._get_ray_moves(r, c, player, [(-1, 0), (1, 0), (0, -1), (0, 1)]))
        elif piece.type == 'Q':
            moves.extend(self._get_ray_moves(r, c, player, [
                (-1, -1), (-1, 1), (1, -1), (1, 1),
                (-1, 0), (1, 0), (0, -1), (0, 1)
            ]))
        elif piece.type == 'K':
            moves.extend(self._get_king_moves(r, c, piece))

        return moves

    def _get_ray_moves(self, r: int, c: int, player: int, directions: List[Tuple[int, int]]) -> List[Move]:
        moves = []
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            while is_valid_square(nr, nc):
                target = self.board[nr][nc]
                if target is None:
                    moves.append(Move((r, c), (nr, nc)))
                else:
                    if target.player != player:
                        moves.append(Move((r, c), (nr, nc)))
                    break
                nr += dr
                nc += dc
        return moves

    def _should_promote(self, piece: Piece, r: int, c: int) -> bool:
        """
        Determines if a pawn at (r, c) should promote.
        In 4PC, pawns promote when reaching the 8th rank from their home rank,
        or reaching an edge where they cannot advance further.
        """
        if piece.player == PLAYER_CYAN:
            return r <= 5  # Advanced 8 ranks up (13 -> 12 -> 11 -> 10 -> 9 -> 8 -> 7 -> 6/5)
        elif piece.player == PLAYER_MAGENTA:
            return c >= 8  # Advanced 8 ranks right
        elif piece.player == PLAYER_LIME:
            return r >= 8  # Advanced 8 ranks down
        elif piece.player == PLAYER_GOLD:
            return c <= 5  # Advanced 8 ranks left
        return False

    def _get_pawn_moves(self, r: int, c: int, piece: Piece) -> List[Move]:
        moves = []
        player = piece.player

        # Direction vector and initial starting row/col
        if player == PLAYER_CYAN:
            f_dr, f_dc = -1, 0
            is_start = (r == 12)
            diag_attacks = [(-1, -1), (-1, 1)]
        elif player == PLAYER_MAGENTA:
            f_dr, f_dc = 0, 1
            is_start = (c == 1)
            diag_attacks = [(-1, 1), (1, 1)]
        elif player == PLAYER_LIME:
            f_dr, f_dc = 1, 0
            is_start = (r == 1)
            diag_attacks = [(1, -1), (1, 1)]
        else:  # PLAYER_GOLD
            f_dr, f_dc = 0, -1
            is_start = (c == 12)
            diag_attacks = [(-1, -1), (1, -1)]

        # 1-step forward
        nr, nc = r + f_dr, c + f_dc
        if is_valid_square(nr, nc) and self.board[nr][nc] is None:
            if self._should_promote(piece, nr, nc):
                for p_type in ['Q', 'R', 'B', 'N']:
                    moves.append(Move((r, c), (nr, nc), promotion=p_type))
            else:
                moves.append(Move((r, c), (nr, nc)))

            # 2-step forward from starting line
            if is_start:
                nnr, nnc = r + 2 * f_dr, c + 2 * f_dc
                if is_valid_square(nnr, nnc) and self.board[nnr][nnc] is None:
                    moves.append(Move((r, c), (nnr, nnc)))

        # Diagonal captures
        for d_dr, d_dc in diag_attacks:
            cr, cc = r + d_dr, c + d_dc
            if is_valid_square(cr, cc):
                target = self.board[cr][cc]
                if target is not None and target.player != player:
                    if self._should_promote(piece, cr, cc):
                        for p_type in ['Q', 'R', 'B', 'N']:
                            moves.append(Move((r, c), (cr, cc), promotion=p_type))
                    else:
                        moves.append(Move((r, c), (cr, cc)))

        return moves

    def _get_king_moves(self, r: int, c: int, piece: Piece) -> List[Move]:
        moves = []
        player = piece.player

        # 8 normal king steps
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if is_valid_square(nr, nc):
                    target = self.board[nr][nc]
                    if target is None or target.player != player:
                        moves.append(Move((r, c), (nr, nc)))

        # Castling
        if not piece.has_moved and not self.is_in_check(player):
            # Check castling with Rooks that haven't moved
            moves.extend(self._get_castling_moves(r, c, player))

        return moves

    def _get_castling_moves(self, k_r: int, k_c: int, player: int) -> List[Move]:
        castling_moves = []
        # Symmetrical castling definitions for each player
        if player == PLAYER_CYAN:
            # Kingside: Rook at (13, 10). Empty at (13, 8), (13, 9). King lands at (13, 9).
            r_ks = self.get_piece(13, 10)
            if r_ks and r_ks.type == 'R' and r_ks.player == player and not r_ks.has_moved:
                if self.board[13][8] is None and self.board[13][9] is None:
                    if not self._is_square_attacked_by_opponents(13, 8, player) and \
                       not self._is_square_attacked_by_opponents(13, 9, player):
                        castling_moves.append(Move((13, 7), (13, 9)))
            # Queenside: Rook at (13, 3). Empty at (13, 4), (13, 5), (13, 6). King lands at (13, 5).
            r_qs = self.get_piece(13, 3)
            if r_qs and r_qs.type == 'R' and r_qs.player == player and not r_qs.has_moved:
                if self.board[13][4] is None and self.board[13][5] is None and self.board[13][6] is None:
                    if not self._is_square_attacked_by_opponents(13, 6, player) and \
                       not self._is_square_attacked_by_opponents(13, 5, player):
                        castling_moves.append(Move((13, 7), (13, 5)))

        elif player == PLAYER_LIME:
            # Kingside: Rook at (0, 10). Empty at (0, 8), (0, 9). King lands at (0, 9).
            r_ks = self.get_piece(0, 10)
            if r_ks and r_ks.type == 'R' and r_ks.player == player and not r_ks.has_moved:
                if self.board[0][8] is None and self.board[0][9] is None:
                    if not self._is_square_attacked_by_opponents(0, 8, player) and \
                       not self._is_square_attacked_by_opponents(0, 9, player):
                        castling_moves.append(Move((0, 7), (0, 9)))
            # Queenside: Rook at (0, 3). Empty at (0, 4), (0, 5), (0, 6). King lands at (0, 5).
            r_qs = self.get_piece(0, 3)
            if r_qs and r_qs.type == 'R' and r_qs.player == player and not r_qs.has_moved:
                if self.board[0][4] is None and self.board[0][5] is None and self.board[0][6] is None:
                    if not self._is_square_attacked_by_opponents(0, 6, player) and \
                       not self._is_square_attacked_by_opponents(0, 5, player):
                        castling_moves.append(Move((0, 7), (0, 5)))

        elif player == PLAYER_MAGENTA:
            # West King at (7, 0).
            # Bottom Rook at (10, 0). Empty at (8, 0), (9, 0). King lands at (9, 0).
            r_b = self.get_piece(10, 0)
            if r_b and r_b.type == 'R' and r_b.player == player and not r_b.has_moved:
                if self.board[8][0] is None and self.board[9][0] is None:
                    if not self._is_square_attacked_by_opponents(8, 0, player) and \
                       not self._is_square_attacked_by_opponents(9, 0, player):
                        castling_moves.append(Move((7, 0), (9, 0)))
            # Top Rook at (3, 0). Empty at (4, 0), (5, 0), (6, 0). King lands at (5, 0).
            r_t = self.get_piece(3, 0)
            if r_t and r_t.type == 'R' and r_t.player == player and not r_t.has_moved:
                if self.board[4][0] is None and self.board[5][0] is None and self.board[6][0] is None:
                    if not self._is_square_attacked_by_opponents(6, 0, player) and \
                       not self._is_square_attacked_by_opponents(5, 0, player):
                        castling_moves.append(Move((7, 0), (5, 0)))

        elif player == PLAYER_GOLD:
            # East King at (7, 13).
            # Bottom Rook at (10, 13). Empty at (8, 13), (9, 13). King lands at (9, 13).
            r_b = self.get_piece(10, 13)
            if r_b and r_b.type == 'R' and r_b.player == player and not r_b.has_moved:
                if self.board[8][13] is None and self.board[9][13] is None:
                    if not self._is_square_attacked_by_opponents(8, 13, player) and \
                       not self._is_square_attacked_by_opponents(9, 13, player):
                        castling_moves.append(Move((7, 13), (9, 13)))
            # Top Rook at (3, 13). Empty at (4, 13), (5, 13), (6, 13). King lands at (5, 13).
            r_t = self.get_piece(3, 13)
            if r_t and r_t.type == 'R' and r_t.player == player and not r_t.has_moved:
                if self.board[4][13] is None and self.board[5][13] is None and self.board[6][13] is None:
                    if not self._is_square_attacked_by_opponents(6, 13, player) and \
                       not self._is_square_attacked_by_opponents(5, 13, player):
                        castling_moves.append(Move((7, 13), (5, 13)))

        return castling_moves

    def _is_square_attacked_by_opponents(self, r: int, c: int, player: int) -> bool:
        for opp in self.active_players:
            if opp != player:
                if self.is_square_attacked(r, c, by_player=opp):
                    return True
        return False

    def get_legal_moves(self, player: Optional[int] = None) -> List[Move]:
        """
        Returns all strictly legal moves for `player` (defaults to current_turn).
        A move is strictly legal if making it does not leave the player's King in check.
        """
        if player is None:
            player = self.current_turn

        if player not in self.active_players or self.is_game_over:
            return []

        legal_moves = []
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                p = self.board[r][c]
                if p and p.player == player and not p.is_dormant:
                    pseudo_moves = self.get_pseudo_legal_moves(r, c)
                    for move in pseudo_moves:
                        if self._is_move_safe_for_king(move, player):
                            legal_moves.append(move)

        return legal_moves

    def _is_move_safe_for_king(self, move: Move, player: int) -> bool:
        """Simulates the move on a cloned state and checks if player's King is safe."""
        from_r, from_c = move.from_sq
        to_r, to_c = move.to_sq

        piece = self.board[from_r][from_c]
        target = self.board[to_r][to_c]

        # Make temporary move
        self.board[to_r][to_c] = piece
        self.board[from_r][from_c] = None

        # Check if King is in check
        in_check = self.is_in_check(player)

        # Revert
        self.board[from_r][from_c] = piece
        self.board[to_r][to_c] = target

        return not in_check

    def make_move(self, move: Move) -> Tuple[bool, str]:
        """
        Executes a move for the current player after full verification.
        Handles captures, castling, promotion, checkmate elimination, and turn progression.
        Returns (success: bool, message: str).
        """
        if self.is_game_over:
            return False, "Game is already over"

        # Check if move is in legal moves
        legal_moves = self.get_legal_moves(self.current_turn)
        matched_move = None
        for m in legal_moves:
            if m.from_sq == move.from_sq and m.to_sq == move.to_sq:
                # If promotion is specified or required
                if m.promotion is not None:
                    if move.promotion is None or move.promotion == m.promotion:
                        matched_move = m
                        break
                else:
                    matched_move = m
                    break

        if not matched_move:
            return False, f"Illegal move for Player {self.current_turn}"

        from_r, from_c = matched_move.from_sq
        to_r, to_c = matched_move.to_sq
        piece = self.board[from_r][from_c]
        target = self.board[to_r][to_c]

        # Record move for history / undo
        move_record = {
            "player": self.current_turn,
            "from": [from_r, from_c],
            "to": [to_r, to_c],
            "piece": piece.to_dict() if piece else None,
            "captured": target.to_dict() if target else None,
            "promotion": matched_move.promotion,
            "halfmove_clock": self.halfmove_clock,
            "turn_number": self.turn_number
        }

        # Handle Castling Rook Movement
        is_castling = False
        if piece.type == 'K' and abs(to_c - from_c) > 1 or (piece.type == 'K' and abs(to_r - from_r) > 1):
            is_castling = True
            self._handle_castling_rook(from_r, from_c, to_r, to_c, piece.player)

        # Handle Captures
        if target is not None:
            self.captured_pieces[self.current_turn].append(target.type)
            self.halfmove_clock = 0
            # If a King was captured directly (e.g. in variants where King is captured)
            if target.type == 'K':
                self.eliminate_player(target.player, reason="King Captured")
        elif piece.type == 'P':
            self.halfmove_clock = 0
        else:
            self.halfmove_clock += 1

        # Move the piece
        self.board[to_r][to_c] = piece
        self.board[from_r][from_c] = None
        piece.has_moved = True

        # Handle Promotion
        if matched_move.promotion:
            piece.type = matched_move.promotion

        self.last_move = matched_move
        self.move_history.append(move_record)

        # Advance Turn & Check Game Status
        self._advance_turn()

        return True, "Move executed successfully"

    def _handle_castling_rook(self, k_from_r: int, k_from_c: int, k_to_r: int, k_to_c: int, player: int):
        """Moves the associated Rook when a King castles."""
        if player == PLAYER_CYAN:
            if k_to_c == 9: # Kingside: Rook (13, 10) -> (13, 8)
                rook = self.board[13][10]
                self.board[13][8] = rook
                self.board[13][10] = None
                if rook: rook.has_moved = True
            elif k_to_c == 5: # Queenside: Rook (13, 3) -> (13, 6)
                rook = self.board[13][3]
                self.board[13][6] = rook
                self.board[13][3] = None
                if rook: rook.has_moved = True
        elif player == PLAYER_LIME:
            if k_to_c == 9: # Kingside: Rook (0, 10) -> (0, 8)
                rook = self.board[0][10]
                self.board[0][8] = rook
                self.board[0][10] = None
                if rook: rook.has_moved = True
            elif k_to_c == 5: # Queenside: Rook (0, 3) -> (0, 6)
                rook = self.board[0][3]
                self.board[0][6] = rook
                self.board[0][3] = None
                if rook: rook.has_moved = True
        elif player == PLAYER_MAGENTA:
            if k_to_r == 9: # Bottom: Rook (10, 0) -> (8, 0)
                rook = self.board[10][0]
                self.board[8][0] = rook
                self.board[10][0] = None
                if rook: rook.has_moved = True
            elif k_to_r == 5: # Top: Rook (3, 0) -> (6, 0)
                rook = self.board[3][0]
                self.board[6][0] = rook
                self.board[3][0] = None
                if rook: rook.has_moved = True
        elif player == PLAYER_GOLD:
            if k_to_r == 9: # Bottom: Rook (10, 13) -> (8, 13)
                rook = self.board[10][13]
                self.board[8][13] = rook
                self.board[10][13] = None
                if rook: rook.has_moved = True
            elif k_to_r == 5: # Top: Rook (3, 13) -> (6, 13)
                rook = self.board[3][13]
                self.board[6][13] = rook
                self.board[3][13] = None
                if rook: rook.has_moved = True

    def eliminate_player(self, player: int, reason: str = "Eliminated") -> None:
        """Eliminates a player: their King is removed, remaining pieces become dormant neutral obstacles."""
        if player in self.eliminated_players:
            return

        self.eliminated_players.append(player)
        if player in self.active_players:
            self.active_players.remove(player)

        # Make all player pieces dormant and remove King
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                p = self.board[r][c]
                if p and p.player == player:
                    if p.type == 'K':
                        self.board[r][c] = None  # Remove king
                    else:
                        p.is_dormant = True      # Greyed out / neutral obstacle

        # Check if victory condition met (only 1 player remains)
        if len(self.active_players) <= 1:
            self.is_game_over = True
            self.winner = self.active_players[0] if len(self.active_players) == 1 else None

    def resign_player(self, player: int) -> Tuple[bool, str]:
        """Player resigns voluntarily."""
        if player not in self.active_players:
            return False, "Player is not currently active"

        self.eliminate_player(player, reason="Resigned")

        # If it was this player's turn, advance to next active player
        if self.current_turn == player and not self.is_game_over:
            self._advance_turn()

        return True, f"Player {player} has resigned"

    def _advance_turn(self) -> None:
        """Passes turn clockwise to next active player, resolving checkmates and draw conditions."""
        if len(self.active_players) <= 1:
            self.is_game_over = True
            self.winner = self.active_players[0] if len(self.active_players) == 1 else None
            return

        # Advance turn cyclically: 1 -> 2 -> 3 -> 4 -> 1
        next_turn = self.current_turn
        found = False
        for _ in range(4):
            next_turn = (next_turn % 4) + 1
            if next_turn in self.active_players:
                found = True
                break

        if not found:
            self.is_game_over = True
            self.winner = None
            return

        self.current_turn = next_turn
        self.turn_number += 1

        # Check if newly active player has legal moves or is checkmated/stalemated
        legal_moves = self.get_legal_moves(self.current_turn)
        if len(legal_moves) == 0:
            if self.is_in_check(self.current_turn):
                # Checkmate!
                eliminated_p = self.current_turn
                self.eliminate_player(eliminated_p, reason="Checkmated")
                if not self.is_game_over:
                    self._advance_turn()
            else:
                # Stalemate: skip turn if player has no moves but not in check
                if not self.is_game_over and len(self.active_players) > 1:
                    self._advance_turn()

    def undo_move(self) -> Tuple[bool, str]:
        """Undoes the previous move (supported for Local mode)."""
        if not self.move_history:
            return False, "No moves to undo"

        last_rec = self.move_history.pop()
        player = last_rec["player"]
        from_r, from_c = last_rec["from"]
        to_r, to_c = last_rec["to"]
        piece_dict = last_rec["piece"]
        captured_dict = last_rec["captured"]

        # Restore piece at from_sq
        self.board[from_r][from_c] = Piece.from_dict(piece_dict)

        # Restore target at to_sq
        if captured_dict:
            self.board[to_r][to_c] = Piece.from_dict(captured_dict)
            if self.captured_pieces[player]:
                self.captured_pieces[player].pop()
        else:
            self.board[to_r][to_c] = None

        self.halfmove_clock = last_rec["halfmove_clock"]
        self.turn_number = last_rec["turn_number"]
        self.current_turn = player
        self.is_game_over = False
        self.winner = None

        # Recompute active players
        active = []
        for p in range(1, 5):
            if self.find_king(p) is not None:
                active.append(p)
        self.active_players = active
        self.eliminated_players = [p for p in range(1, 5) if p not in self.active_players]

        # Update last move
        if self.move_history:
            prev = self.move_history[-1]
            self.last_move = Move(tuple(prev["from"]), tuple(prev["to"]), prev.get("promotion"))
        else:
            self.last_move = None

        return True, "Move undone"

    def get_state(self) -> Dict[str, Any]:
        """Serializes current engine state into a complete JSON-serializable dictionary."""
        grid = []
        for r in range(BOARD_SIZE):
            row_data = []
            for c in range(BOARD_SIZE):
                if not is_valid_square(r, c):
                    row_data.append("VOID")
                else:
                    p = self.board[r][c]
                    row_data.append(p.to_dict() if p else None)
            grid.append(row_data)

        # Generate legal moves for current player
        current_legal_moves = [m.to_dict() for m in self.get_legal_moves(self.current_turn)]

        # Check status for all players
        check_status = {p: self.is_in_check(p) for p in range(1, 5)}

        return {
            "board": grid,
            "current_turn": self.current_turn,
            "active_players": self.active_players,
            "eliminated_players": self.eliminated_players,
            "winner": self.winner,
            "is_game_over": self.is_game_over,
            "turn_number": self.turn_number,
            "captured_pieces": self.captured_pieces,
            "legal_moves": current_legal_moves,
            "last_move": self.last_move.to_dict() if self.last_move else None,
            "check_status": check_status
        }
