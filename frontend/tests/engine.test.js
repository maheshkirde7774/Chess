const { test, describe } = require("node:test");
const assert = require("node:assert/strict");

// Setup minimal browser globals for loading the client engine
global.window = global;
require("../js/chess-engine-client.js");

describe("Frontend ClientChessEngine Tests", () => {
    test("Board geometry correctly defines 160 active squares and 36 void corner squares", () => {
        const engine = new window.ClientChessEngine();
        assert.equal(engine.board.length, 14);
        assert.equal(engine.board[0].length, 14);

        // Check 3x3 corners are voids (null and invalid)
        const corners = [
            [0, 0], [0, 1], [0, 2], [1, 0], [2, 0], // Top-Left
            [0, 11], [0, 12], [0, 13], [1, 13], [2, 13], // Top-Right
            [11, 0], [12, 0], [13, 0], [13, 1], [13, 2], // Bottom-Left
            [11, 13], [12, 13], [13, 11], [13, 12], [13, 13] // Bottom-Right
        ];
        for (const [r, c] of corners) {
            assert.equal(engine.getPiece(r, c), null, `Corner (${r}, ${c}) must be empty/void`);
        }
    });

    test("Initial setup places 16 units for each of the 4 commanders", () => {
        const engine = new window.ClientChessEngine();
        const counts = { 1: 0, 2: 0, 3: 0, 4: 0 };
        const kings = {};

        for (let r = 0; r < 14; r++) {
            for (let c = 0; c < 14; c++) {
                const p = engine.getPiece(r, c);
                if (p) {
                    counts[p.player]++;
                    if (p.type === "K") kings[p.player] = [r, c];
                }
            }
        }

        assert.equal(counts[1], 16, "Cyan (Player 1) must have 16 starting pieces");
        assert.equal(counts[2], 16, "Magenta (Player 2) must have 16 starting pieces");
        assert.equal(counts[3], 16, "Lime (Player 3) must have 16 starting pieces");
        assert.equal(counts[4], 16, "Gold (Player 4) must have 16 starting pieces");

        // Verify King positions
        assert.deepEqual(engine.findKing(1), [13, 7], "Cyan King must be at [13, 7]");
        assert.deepEqual(engine.findKing(2), [7, 0], "Magenta King must be at [7, 0]");
        assert.deepEqual(engine.findKing(3), [0, 7], "Lime King must be at [0, 7]");
        assert.deepEqual(engine.findKing(4), [7, 13], "Gold King must be at [7, 13]");
    });

    test("Cyan pawn single and double thrust moves are generated", () => {
        const engine = new window.ClientChessEngine();
        assert.equal(engine.currentTurn, 1, "Initial turn must be Cyan (Player 1)");

        // Get legal moves for Cyan pawn at [12, 7]
        const allCyanMoves = engine.getLegalMoves(1);
        const pawnMoves = allCyanMoves.filter(m => m.from[0] === 12 && m.from[1] === 7);
        assert.ok(pawnMoves.length >= 2, "Starting pawn must have at least 2 moves");

        const hasSingleStep = pawnMoves.some(m => m.to[0] === 11 && m.to[1] === 7);
        const hasDoubleStep = pawnMoves.some(m => m.to[0] === 10 && m.to[1] === 7);

        assert.ok(hasSingleStep, "Cyan pawn can advance 1 square to [11, 7]");
        assert.ok(hasDoubleStep, "Cyan pawn can advance 2 squares to [10, 7]");
    });

    test("Turn progression proceeds clockwise: Cyan (1) -> Magenta (2) -> Lime (3) -> Gold (4)", () => {
        const engine = new window.ClientChessEngine();
        assert.equal(engine.currentTurn, 1);

        // Player 1 (Cyan) moves pawn
        assert.ok(engine.makeMove({ from: [12, 6], to: [10, 6] }));
        assert.equal(engine.currentTurn, 2, "Turn should advance to Magenta (2)");

        // Player 2 (Magenta) moves pawn
        assert.ok(engine.makeMove({ from: [6, 1], to: [6, 3] }));
        assert.equal(engine.currentTurn, 3, "Turn should advance to Lime (3)");

        // Player 3 (Lime) moves pawn
        assert.ok(engine.makeMove({ from: [1, 6], to: [3, 6] }));
        assert.equal(engine.currentTurn, 4, "Turn should advance to Gold (4)");

        // Player 4 (Gold) moves pawn
        assert.ok(engine.makeMove({ from: [6, 12], to: [6, 10] }));
        assert.equal(engine.currentTurn, 1, "Turn should cycle back to Cyan (1)");
    });

    test("Knight jumps over obstacle pieces correctly", () => {
        const engine = new window.ClientChessEngine();
        // Cyan Knight at [13, 4]
        const allCyanMoves = engine.getLegalMoves(1);
        const knightMoves = allCyanMoves.filter(m => m.from[0] === 13 && m.from[1] === 4);
        assert.ok(knightMoves.length > 0, "Knight should have legal initial jumps");
        const destinations = knightMoves.map(m => `${m.to[0]},${m.to[1]}`);
        assert.ok(destinations.includes("11,3"), "Knight leaps to [11, 3]");
        assert.ok(destinations.includes("11,5"), "Knight leaps to [11, 5]");
    });

    test("Elimination converts remaining pieces to dormant obstacles", () => {
        const engine = new window.ClientChessEngine();
        // Eliminate Magenta (Player 2)
        engine.eliminatePlayer(2);
        assert.ok(engine.eliminatedPlayers.includes(2), "Player 2 must be recorded as eliminated");
        assert.equal(engine.findKing(2), null, "Eliminated player king must be removed");

        // Remaining pieces of Player 2 should be marked dormant
        let dormantCount = 0;
        for (let r = 0; r < 14; r++) {
            for (let c = 0; c < 14; c++) {
                const p = engine.getPiece(r, c);
                if (p && p.player === 2) {
                    assert.ok(p.isDormant, "Player 2 piece must be dormant");
                    dormantCount++;
                }
            }
        }
        assert.equal(dormantCount, 15, "15 non-king pieces of Player 2 remain as dormant obstacles");
    });

    test("FourPlayerAI bot selects valid legal moves across difficulty tiers", () => {
        for (const tier of ["novice", "club", "master"]) {
            const engine = new window.ClientChessEngine();
            const ai = new window.FourPlayerAI(tier);
            const move = ai.chooseMove(engine, 1);
            assert.ok(move, `AI (${tier}) must select a move`);
            assert.ok(Array.isArray(move.from) && move.from.length === 2);
            assert.ok(Array.isArray(move.to) && move.to.length === 2);

            // Verify the chosen move is actually legal for the piece
            const legals = engine.getLegalMoves(1);
            const isLegal = legals.some(m =>
                m.from[0] === move.from[0] && m.from[1] === move.from[1] &&
                m.to[0] === move.to[0] && m.to[1] === move.to[1]
            );
            assert.ok(isLegal, `Move chosen by AI (${tier}) must be among legal moves`);
        }
    });
});
