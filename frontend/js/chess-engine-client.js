/**
 * Neon Four Chess - Client-Side 4-Player Chess Engine Mirror
 * Provides instantaneous move generation, validation, and local play mechanics.
 */

const BOARD_SIZE = 14;

// 3x3 corner voids
const CUTOUTS = new Set();
for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
        CUTOUTS.add(`${r},${c}`);
        CUTOUTS.add(`${r},${13 - c}`);
        CUTOUTS.add(`${13 - r},${c}`);
        CUTOUTS.add(`${13 - r},${13 - c}`);
    }
}

function isValidSquare(r, c) {
    if (r >= 0 && r < BOARD_SIZE && c >= 0 && c < BOARD_SIZE) {
        return !CUTOUTS.has(`${r},${c}`);
    }
    return false;
}

const PLAYER_CYAN = 1;
const PLAYER_MAGENTA = 2;
const PLAYER_LIME = 3;
const PLAYER_GOLD = 4;

const PLAYER_INFO = {
    [PLAYER_CYAN]: { name: "Cyan", side: "South", color: "#00f3ff", bg: "rgba(0, 243, 255, 0.15)" },
    [PLAYER_MAGENTA]: { name: "Magenta", side: "West", color: "#ff007f", bg: "rgba(255, 0, 127, 0.15)" },
    [PLAYER_LIME]: { name: "Lime", side: "North", color: "#39ff14", bg: "rgba(57, 255, 20, 0.15)" },
    [PLAYER_GOLD]: { name: "Gold", side: "East", color: "#ffd700", bg: "rgba(255, 215, 0, 0.15)" }
};

class ClientChessEngine {
    constructor() {
        this.board = Array.from({ length: BOARD_SIZE }, () => Array(BOARD_SIZE).fill(null));
        this.currentTurn = PLAYER_CYAN;
        this.activePlayers = [PLAYER_CYAN, PLAYER_MAGENTA, PLAYER_LIME, PLAYER_GOLD];
        this.eliminatedPlayers = [];
        this.winner = null;
        this.isGameOver = false;
        this.moveHistory = [];
        this.capturedPieces = { 1: [], 2: [], 3: [], 4: [] };
        this.halfmoveClock = 0;
        this.turnNumber = 1;
        this.lastMove = null;

        this.setupInitialBoard();
    }

    setupInitialBoard() {
        this.board = Array.from({ length: BOARD_SIZE }, () => Array(BOARD_SIZE).fill(null));

        // Player 1: Cyan (South / Bottom)
        const p1Back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'];
        p1Back.forEach((type, idx) => {
            this.board[13][3 + idx] = { type, player: PLAYER_CYAN, hasMoved: false, isDormant: false };
        });
        for (let c = 3; c <= 10; c++) {
            this.board[12][c] = { type: 'P', player: PLAYER_CYAN, hasMoved: false, isDormant: false };
        }

        // Player 3: Lime (North / Top)
        const p3Back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'];
        p3Back.forEach((type, idx) => {
            this.board[0][3 + idx] = { type, player: PLAYER_LIME, hasMoved: false, isDormant: false };
        });
        for (let c = 3; c <= 10; c++) {
            this.board[1][c] = { type: 'P', player: PLAYER_LIME, hasMoved: false, isDormant: false };
        }

        // Player 2: Magenta (West / Left)
        const p2Back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'];
        p2Back.forEach((type, idx) => {
            this.board[3 + idx][0] = { type, player: PLAYER_MAGENTA, hasMoved: false, isDormant: false };
        });
        for (let r = 3; r <= 10; r++) {
            this.board[r][1] = { type: 'P', player: PLAYER_MAGENTA, hasMoved: false, isDormant: false };
        }

        // Player 4: Gold (East / Right)
        const p4Back = ['R', 'N', 'B', 'Q', 'K', 'B', 'N', 'R'];
        p4Back.forEach((type, idx) => {
            this.board[3 + idx][13] = { type, player: PLAYER_GOLD, hasMoved: false, isDormant: false };
        });
        for (let r = 3; r <= 10; r++) {
            this.board[r][12] = { type: 'P', player: PLAYER_GOLD, hasMoved: false, isDormant: false };
        }
    }

    getPiece(r, c) {
        if (isValidSquare(r, c)) {
            return this.board[r][c];
        }
        return null;
    }

    findKing(player) {
        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const p = this.board[r][c];
                if (p && p.player === player && p.type === 'K' && !p.isDormant) {
                    return [r, c];
                }
            }
        }
        return null;
    }

    isSquareAttacked(targetR, targetC, byPlayer = null) {
        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const piece = this.board[r][c];
                if (!piece || piece.isDormant || this.eliminatedPlayers.includes(piece.player)) {
                    continue;
                }
                if (byPlayer !== null && piece.player !== byPlayer) {
                    continue;
                }
                if (this._canPieceAttack(r, c, piece, targetR, targetC)) {
                    return true;
                }
            }
        }
        return false;
    }

    _canPieceAttack(fromR, fromC, piece, toR, toC) {
        const dr = toR - fromR;
        const dc = toC - fromC;

        if (piece.type === 'P') {
            if (piece.player === PLAYER_CYAN) return dr === -1 && Math.abs(dc) === 1;
            if (piece.player === PLAYER_MAGENTA) return dc === 1 && Math.abs(dr) === 1;
            if (piece.player === PLAYER_LIME) return dr === 1 && Math.abs(dc) === 1;
            if (piece.player === PLAYER_GOLD) return dc === -1 && Math.abs(dr) === 1;
            return false;
        }

        if (piece.type === 'N') {
            return (Math.abs(dr) === 1 && Math.abs(dc) === 2) || (Math.abs(dr) === 2 && Math.abs(dc) === 1);
        }

        if (piece.type === 'B') {
            if (Math.abs(dr) === Math.abs(dc) && dr !== 0) {
                const stepR = dr > 0 ? 1 : -1;
                const stepC = dc > 0 ? 1 : -1;
                let curR = fromR + stepR;
                let curC = fromC + stepC;
                while (curR !== toR || curC !== toC) {
                    if (!isValidSquare(curR, curC) || this.board[curR][curC] !== null) return false;
                    curR += stepR;
                    curC += stepC;
                }
                return true;
            }
            return false;
        }

        if (piece.type === 'R') {
            if ((dr === 0 && dc !== 0) || (dc === 0 && dr !== 0)) {
                const stepR = dr === 0 ? 0 : (dr > 0 ? 1 : -1);
                const stepC = dc === 0 ? 0 : (dc > 0 ? 1 : -1);
                let curR = fromR + stepR;
                let curC = fromC + stepC;
                while (curR !== toR || curC !== toC) {
                    if (!isValidSquare(curR, curC) || this.board[curR][curC] !== null) return false;
                    curR += stepR;
                    curC += stepC;
                }
                return true;
            }
            return false;
        }

        if (piece.type === 'Q') {
            if (Math.abs(dr) === Math.abs(dc) && dr !== 0) {
                const stepR = dr > 0 ? 1 : -1;
                const stepC = dc > 0 ? 1 : -1;
                let curR = fromR + stepR;
                let curC = fromC + stepC;
                while (curR !== toR || curC !== toC) {
                    if (!isValidSquare(curR, curC) || this.board[curR][curC] !== null) return false;
                    curR += stepR;
                    curC += stepC;
                }
                return true;
            } else if ((dr === 0 && dc !== 0) || (dc === 0 && dr !== 0)) {
                const stepR = dr === 0 ? 0 : (dr > 0 ? 1 : -1);
                const stepC = dc === 0 ? 0 : (dc > 0 ? 1 : -1);
                let curR = fromR + stepR;
                let curC = fromC + stepC;
                while (curR !== toR || curC !== toC) {
                    if (!isValidSquare(curR, curC) || this.board[curR][curC] !== null) return false;
                    curR += stepR;
                    curC += stepC;
                }
                return true;
            }
            return false;
        }

        if (piece.type === 'K') {
            return Math.max(Math.abs(dr), Math.abs(dc)) === 1;
        }

        return false;
    }

    isInCheck(player) {
        const kingPos = this.findKing(player);
        if (!kingPos) return false;
        for (const opp of this.activePlayers) {
            if (opp !== player) {
                if (this.isSquareAttacked(kingPos[0], kingPos[1], opp)) {
                    return true;
                }
            }
        }
        return false;
    }

    getPseudoLegalMoves(r, c) {
        const piece = this.board[r][c];
        if (!piece || piece.isDormant) return [];

        const moves = [];
        const player = piece.player;

        if (piece.type === 'P') {
            moves.push(...this._getPawnMoves(r, c, piece));
        } else if (piece.type === 'N') {
            const offsets = [
                [-2, -1], [-2, 1], [-1, -2], [-1, 2],
                [1, -2], [1, 2], [2, -1], [2, 1]
            ];
            for (const [dr, dc] of offsets) {
                const nr = r + dr, nc = c + dc;
                if (isValidSquare(nr, nc)) {
                    const target = this.board[nr][nc];
                    if (!target || target.player !== player) {
                        moves.push({ from: [r, c], to: [nr, nc] });
                    }
                }
            }
        } else if (piece.type === 'B') {
            moves.push(...this._getRayMoves(r, c, player, [[-1, -1], [-1, 1], [1, -1], [1, 1]]));
        } else if (piece.type === 'R') {
            moves.push(...this._getRayMoves(r, c, player, [[-1, 0], [1, 0], [0, -1], [0, 1]]));
        } else if (piece.type === 'Q') {
            moves.push(...this._getRayMoves(r, c, player, [
                [-1, -1], [-1, 1], [1, -1], [1, 1],
                [-1, 0], [1, 0], [0, -1], [0, 1]
            ]));
        } else if (piece.type === 'K') {
            moves.push(...this._getKingMoves(r, c, piece));
        }

        return moves;
    }

    _getRayMoves(r, c, player, directions) {
        const moves = [];
        for (const [dr, dc] of directions) {
            let nr = r + dr, nc = c + dc;
            while (isValidSquare(nr, nc)) {
                const target = this.board[nr][nc];
                if (!target) {
                    moves.push({ from: [r, c], to: [nr, nc] });
                } else {
                    if (target.player !== player) {
                        moves.push({ from: [r, c], to: [nr, nc] });
                    }
                    break;
                }
                nr += dr;
                nc += dc;
            }
        }
        return moves;
    }

    _shouldPromote(piece, r, c) {
        if (piece.player === PLAYER_CYAN) return r <= 5;
        if (piece.player === PLAYER_MAGENTA) return c >= 8;
        if (piece.player === PLAYER_LIME) return r >= 8;
        if (piece.player === PLAYER_GOLD) return c <= 5;
        return false;
    }

    _getPawnMoves(r, c, piece) {
        const moves = [];
        const player = piece.player;
        let fDr = 0, fDc = 0, isStart = false, attacks = [];

        if (player === PLAYER_CYAN) {
            fDr = -1; fDc = 0; isStart = (r === 12);
            attacks = [[-1, -1], [-1, 1]];
        } else if (player === PLAYER_MAGENTA) {
            fDr = 0; fDc = 1; isStart = (c === 1);
            attacks = [[-1, 1], [1, 1]];
        } else if (player === PLAYER_LIME) {
            fDr = 1; fDc = 0; isStart = (r === 1);
            attacks = [[1, -1], [1, 1]];
        } else {
            fDr = 0; fDc = -1; isStart = (c === 12);
            attacks = [[-1, -1], [1, -1]];
        }

        // 1-step forward
        const nr = r + fDr, nc = c + fDc;
        if (isValidSquare(nr, nc) && this.board[nr][nc] === null) {
            if (this._shouldPromote(piece, nr, nc)) {
                ['Q', 'R', 'B', 'N'].forEach(promo => {
                    moves.push({ from: [r, c], to: [nr, nc], promotion: promo });
                });
            } else {
                moves.push({ from: [r, c], to: [nr, nc] });
            }

            // 2-step forward
            if (isStart) {
                const nnr = r + 2 * fDr, nnc = c + 2 * fDc;
                if (isValidSquare(nnr, nnc) && this.board[nnr][nnc] === null) {
                    moves.push({ from: [r, c], to: [nnr, nnc] });
                }
            }
        }

        // Diagonal attacks
        for (const [dDr, dDc] of attacks) {
            const cr = r + dDr, cc = c + dDc;
            if (isValidSquare(cr, cc)) {
                const target = this.board[cr][cc];
                if (target !== null && target.player !== player) {
                    if (this._shouldPromote(piece, cr, cc)) {
                        ['Q', 'R', 'B', 'N'].forEach(promo => {
                            moves.push({ from: [r, c], to: [cr, cc], promotion: promo });
                        });
                    } else {
                        moves.push({ from: [r, c], to: [cr, cc] });
                    }
                }
            }
        }

        return moves;
    }

    _getKingMoves(r, c, piece) {
        const moves = [];
        const player = piece.player;

        for (let dr = -1; dr <= 1; dr++) {
            for (let dc = -1; dc <= 1; dc++) {
                if (dr === 0 && dc === 0) continue;
                const nr = r + dr, nc = c + dc;
                if (isValidSquare(nr, nc)) {
                    const target = this.board[nr][nc];
                    if (!target || target.player !== player) {
                        moves.push({ from: [r, c], to: [nr, nc] });
                    }
                }
            }
        }

        // Castling
        if (!piece.hasMoved && !this.isInCheck(player)) {
            moves.push(...this._getCastlingMoves(r, c, player));
        }

        return moves;
    }

    _getCastlingMoves(kR, kC, player) {
        const castling = [];
        if (player === PLAYER_CYAN) {
            const rKs = this.getPiece(13, 10);
            if (rKs && rKs.type === 'R' && rKs.player === player && !rKs.hasMoved) {
                if (!this.board[13][8] && !this.board[13][9]) {
                    if (!this._isAttackedByOpponents(13, 8, player) && !this._isAttackedByOpponents(13, 9, player)) {
                        castling.push({ from: [13, 7], to: [13, 9] });
                    }
                }
            }
            const rQs = this.getPiece(13, 3);
            if (rQs && rQs.type === 'R' && rQs.player === player && !rQs.hasMoved) {
                if (!this.board[13][4] && !this.board[13][5] && !this.board[13][6]) {
                    if (!this._isAttackedByOpponents(13, 6, player) && !this._isAttackedByOpponents(13, 5, player)) {
                        castling.push({ from: [13, 7], to: [13, 5] });
                    }
                }
            }
        }
        return castling;
    }

    _isAttackedByOpponents(r, c, player) {
        for (const opp of this.activePlayers) {
            if (opp !== player && this.isSquareAttacked(r, c, opp)) return true;
        }
        return false;
    }

    getLegalMoves(player = null) {
        if (player === null) player = this.currentTurn;
        if (!this.activePlayers.includes(player) || this.isGameOver) return [];

        const legal = [];
        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const p = this.board[r][c];
                if (p && p.player === player && !p.isDormant) {
                    const pseudos = this.getPseudoLegalMoves(r, c);
                    for (const m of pseudos) {
                        if (this._isMoveSafeForKing(m, player)) {
                            legal.push(m);
                        }
                    }
                }
            }
        }
        return legal;
    }

    _isMoveSafeForKing(move, player) {
        const [fromR, fromC] = move.from;
        const [toR, toC] = move.to;

        const piece = this.board[fromR][fromC];
        const target = this.board[toR][toC];

        this.board[toR][toC] = piece;
        this.board[fromR][fromC] = null;

        const inCheck = this.isInCheck(player);

        this.board[fromR][fromC] = piece;
        this.board[toR][toC] = target;

        return !inCheck;
    }

    makeMove(move) {
        if (this.isGameOver) return { success: false, message: "Game over" };

        const [fromR, fromC] = move.from;
        const [toR, toC] = move.to;
        const piece = this.board[fromR][fromC];
        const target = this.board[toR][toC];

        if (!piece || piece.player !== this.currentTurn) {
            return { success: false, message: "Invalid player piece" };
        }

        // Verify with legal moves
        const legalMoves = this.getLegalMoves(this.currentTurn);
        const match = legalMoves.find(m =>
            m.from[0] === fromR && m.from[1] === fromC &&
            m.to[0] === toR && m.to[1] === toC &&
            (!m.promotion || m.promotion === (move.promotion || 'Q'))
        );

        if (!match) return { success: false, message: "Illegal move" };

        const record = {
            player: this.currentTurn,
            from: [fromR, fromC],
            to: [toR, toC],
            piece: { ...piece },
            captured: target ? { ...target } : null,
            promotion: match.promotion,
            halfmoveClock: this.halfmoveClock,
            turnNumber: this.turnNumber
        };

        // Castling rook move
        if (piece.type === 'K' && Math.abs(toC - fromC) > 1) {
            if (toC === 9) { // Kingside
                const rook = this.board[13][10];
                this.board[13][8] = rook;
                this.board[13][10] = null;
                if (rook) rook.hasMoved = true;
            } else if (toC === 5) { // Queenside
                const rook = this.board[13][3];
                this.board[13][6] = rook;
                this.board[13][3] = null;
                if (rook) rook.hasMoved = true;
            }
        }

        // Captures
        if (target) {
            this.capturedPieces[this.currentTurn].push(target.type);
            this.halfmoveClock = 0;
            if (target.type === 'K') {
                this.eliminatePlayer(target.player);
            }
        } else if (piece.type === 'P') {
            this.halfmoveClock = 0;
        } else {
            this.halfmoveClock++;
        }

        this.board[toR][toC] = piece;
        this.board[fromR][fromC] = null;
        piece.hasMoved = true;

        if (match.promotion) {
            piece.type = match.promotion;
        }

        this.lastMove = match;
        this.moveHistory.push(record);

        this._advanceTurn();

        return { success: true, message: "Move executed" };
    }

    eliminatePlayer(player) {
        if (this.eliminatedPlayers.includes(player)) return;
        this.eliminatedPlayers.push(player);
        this.activePlayers = this.activePlayers.filter(p => p !== player);

        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const p = this.board[r][c];
                if (p && p.player === player) {
                    if (p.type === 'K') {
                        this.board[r][c] = null;
                    } else {
                        p.isDormant = true;
                    }
                }
            }
        }

        if (this.activePlayers.length <= 1) {
            this.isGameOver = true;
            this.winner = this.activePlayers.length === 1 ? this.activePlayers[0] : null;
        }
    }

    resignPlayer(player) {
        if (!this.activePlayers.includes(player)) return { success: false, message: "Not active" };
        this.eliminatePlayer(player);
        if (this.currentTurn === player && !this.isGameOver) {
            this._advanceTurn();
        }
        return { success: true, message: `Player ${player} resigned` };
    }

    _advanceTurn() {
        if (this.activePlayers.length <= 1) {
            this.isGameOver = true;
            this.winner = this.activePlayers[0] || null;
            return;
        }

        let next = this.currentTurn;
        for (let i = 0; i < 4; i++) {
            next = (next % 4) + 1;
            if (this.activePlayers.includes(next)) break;
        }

        this.currentTurn = next;
        this.turnNumber++;

        const legal = this.getLegalMoves(this.currentTurn);
        if (legal.length === 0) {
            if (this.isInCheck(this.currentTurn)) {
                this.eliminatePlayer(this.currentTurn);
                if (!this.isGameOver) this._advanceTurn();
            } else {
                if (!this.isGameOver && this.activePlayers.length > 1) this._advanceTurn();
            }
        }
    }

    undoMove() {
        if (!this.moveHistory.length) return { success: false, message: "No moves" };
        const last = this.moveHistory.pop();
        const [fromR, fromC] = last.from;
        const [toR, toC] = last.to;

        this.board[fromR][fromC] = { ...last.piece };
        if (last.captured) {
            this.board[toR][toC] = { ...last.captured };
            this.capturedPieces[last.player].pop();
        } else {
            this.board[toR][toC] = null;
        }

        this.currentTurn = last.player;
        this.halfmoveClock = last.halfmoveClock;
        this.turnNumber = last.turnNumber;
        this.isGameOver = false;
        this.winner = null;

        const active = [];
        for (let p = 1; p <= 4; p++) {
            if (this.findKing(p) !== null) active.push(p);
        }
        this.activePlayers = active;
        this.eliminatedPlayers = [1, 2, 3, 4].filter(p => !active.includes(p));

        this.lastMove = this.moveHistory.length ? this.moveHistory[this.moveHistory.length - 1] : null;

        return { success: true, message: "Undone" };
    }

    syncFromServerState(serverState) {
        if (!serverState) return;
        // Reconstruct board from 2D array
        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const sq = serverState.board[r][c];
                if (sq === "VOID" || sq === null) {
                    this.board[r][c] = null;
                } else {
                    this.board[r][c] = {
                        type: sq.type,
                        player: sq.player,
                        hasMoved: sq.has_moved || false,
                        isDormant: sq.is_dormant || false
                    };
                }
            }
        }

        this.currentTurn = serverState.current_turn;
        this.activePlayers = serverState.active_players || [1, 2, 3, 4];
        this.eliminatedPlayers = serverState.eliminated_players || [];
        this.winner = serverState.winner;
        this.isGameOver = serverState.is_game_over || false;
        this.turnNumber = serverState.turn_number || 1;
        this.capturedPieces = serverState.captured_pieces || { 1: [], 2: [], 3: [], 4: [] };
        if (serverState.last_move) {
            this.lastMove = {
                from: serverState.last_move.from,
                to: serverState.last_move.to,
                promotion: serverState.last_move.promotion
            };
        } else {
            this.lastMove = null;
        }
    }
}

window.ClientChessEngine = ClientChessEngine;
window.PLAYER_INFO = PLAYER_INFO;
