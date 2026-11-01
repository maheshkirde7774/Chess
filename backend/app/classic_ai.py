"""Bounded alpha-beta chess opponent for the Classic game."""

import random
import threading
import time
from dataclasses import dataclass
from typing import Optional

import chess

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 335,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}
MATE_SCORE = 100_000
INFINITY = 1_000_000


@dataclass(frozen=True)
class Difficulty:
    depth: int
    max_nodes: int
    think_seconds: float
    beginner_variance: int = 0


DIFFICULTIES = {
    "beginner": Difficulty(depth=1, max_nodes=500, think_seconds=0.08, beginner_variance=180),
    "intermediate": Difficulty(depth=2, max_nodes=3_000, think_seconds=0.25),
    "advanced": Difficulty(depth=3, max_nodes=14_000, think_seconds=0.7),
    "expert": Difficulty(depth=5, max_nodes=45_000, think_seconds=1.5),
}


@dataclass
class Search:
    cancel: threading.Event
    deadline: float
    max_nodes: int
    nodes: int = 0
    aborted: bool = False

    def should_stop(self) -> bool:
        if self.cancel.is_set() or self.nodes >= self.max_nodes or time.monotonic() >= self.deadline:
            self.aborted = True
        return self.aborted


def _piece_square_bonus(piece: chess.Piece, square: chess.Square) -> int:
    file_index = chess.square_file(square)
    rank_index = chess.square_rank(square)
    advancement = rank_index if piece.color == chess.WHITE else 7 - rank_index
    center_distance = abs(3.5 - file_index) + abs(3.5 - rank_index)
    center = int((7 - center_distance) * 4)
    if piece.piece_type == chess.PAWN:
        return advancement * 7 + center // 3
    if piece.piece_type in (chess.KNIGHT, chess.BISHOP):
        return center
    if piece.piece_type == chess.ROOK:
        return advancement * 2
    if piece.piece_type == chess.QUEEN:
        return center // 2
    return -center if piece.color == chess.WHITE and rank_index == 0 else 0


def evaluate(board: chess.Board) -> int:
    """Returns a centipawn score from the side-to-move's perspective."""
    outcome = board.outcome(claim_draw=False)
    if outcome is not None:
        if outcome.winner is None:
            return 0
        return MATE_SCORE if outcome.winner == board.turn else -MATE_SCORE

    white_score = 0
    for square, piece in board.piece_map().items():
        value = PIECE_VALUES[piece.piece_type] + _piece_square_bonus(piece, square)
        white_score += value if piece.color == chess.WHITE else -value

    score = white_score if board.turn == chess.WHITE else -white_score
    if board.is_check():
        score -= 25
    return max(0, score) if board.can_claim_draw() else score


def _move_order_score(board: chess.Board, move: chess.Move) -> int:
    score = 0
    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        if board.is_en_passant(move):
            victim_value = PIECE_VALUES[chess.PAWN]
        else:
            victim_value = PIECE_VALUES[victim.piece_type] if victim else 0
        attacker = board.piece_at(move.from_square)
        attacker_value = PIECE_VALUES[attacker.piece_type] if attacker else 0
        score += 10_000 + victim_value * 10 - attacker_value
    if move.promotion:
        score += 8_000 + PIECE_VALUES[move.promotion]
    return score


def _negamax(
    board: chess.Board,
    depth: int,
    alpha: int,
    beta: int,
    ply: int,
    search: Search,
) -> int:
    search.nodes += 1
    if search.should_stop():
        return evaluate(board)

    outcome = board.outcome(claim_draw=False)
    if outcome is not None:
        if outcome.winner is None:
            return 0
        return -MATE_SCORE + ply if outcome.winner != board.turn else MATE_SCORE - ply
    if depth <= 0:
        return evaluate(board)

    can_claim_draw = board.can_claim_draw()
    best = 0 if can_claim_draw else -INFINITY
    moves = sorted(board.legal_moves, key=lambda move: _move_order_score(board, move), reverse=True)
    for move in moves:
        board.push(move)
        score = -_negamax(board, depth - 1, -beta, -alpha, ply + 1, search)
        board.pop()
        if score > best:
            best = score
        if score > alpha:
            alpha = score
        if alpha >= beta or search.should_stop():
            break
    return best


def choose_move(
    board: chess.Board,
    difficulty: str,
    cancel: Optional[threading.Event] = None,
) -> Optional[chess.Move]:
    """Searches a position off-thread using bounded iterative deepening."""
    config = DIFFICULTIES.get(difficulty)
    if config is None:
        raise ValueError(f"Unknown AI difficulty: {difficulty}")
    if board.is_game_over(claim_draw=False):
        return None

    cancellation = cancel or threading.Event()
    legal_moves = list(board.legal_moves)
    if not legal_moves:
        return None
    search = Search(
        cancel=cancellation,
        deadline=time.monotonic() + config.think_seconds,
        max_nodes=config.max_nodes,
    )
    root = board.copy(stack=True)
    best_move = legal_moves[0]
    completed_scores: list[tuple[int, chess.Move]] = []

    for depth in range(1, config.depth + 1):
        if search.should_stop():
            break
        depth_scores: list[tuple[int, chess.Move]] = []
        ordered_moves = sorted(
            root.legal_moves,
            key=lambda move: _move_order_score(root, move),
            reverse=True,
        )
        for move in ordered_moves:
            if search.should_stop():
                break
            root.push(move)
            score = -_negamax(root, depth - 1, -INFINITY, INFINITY, 1, search)
            root.pop()
            if search.cancel.is_set():
                return None
            depth_scores.append((score, move))

        if depth_scores and not search.aborted:
            completed_scores = depth_scores
            best_move = max(depth_scores, key=lambda item: item[0])[1]
        if search.aborted:
            break

    if search.cancel.is_set():
        return None
    if board.can_claim_draw() and completed_scores:
        if max(score for score, _ in completed_scores) <= 0:
            return None
    if difficulty == "beginner" and completed_scores:
        completed_scores.sort(key=lambda item: item[0], reverse=True)
        best_score = completed_scores[0][0]
        easier_choices = [
            move for score, move in completed_scores
            if score >= best_score - config.beginner_variance
        ]
        return random.choice(easier_choices[: min(5, len(easier_choices))])
    return best_move
