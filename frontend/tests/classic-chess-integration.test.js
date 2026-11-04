const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const mockStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
};

// Mock window, document, storage, and browser environment
globalThis.sessionStorage = mockStorage;
globalThis.localStorage = mockStorage;

globalThis.window = {
    CONFIG: {
        isAudioEnabled: () => true,
        setAudioEnabled: () => {},
        getServerUrl: () => "http://localhost:8000",
        getWsUrl: () => "ws://localhost:8000/ws",
    },
    FOURXProfile: {
        ready: Promise.resolve(),
        authHeaders: () => ({}),
    },
    FOURXCustomization: {
        onSoundEnabledChanged: () => {},
        preferences: {},
    },
    location: { href: "http://localhost:8000" },
    localStorage: mockStorage,
    sessionStorage: mockStorage,
};

globalThis.document = {
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
};

// Load audio.js
const audioCode = fs.readFileSync(path.join(__dirname, "../js/audio.js"), "utf8");
eval(audioCode);

// Load classic-chess.js
const classicCode = fs.readFileSync(path.join(__dirname, "../js/classic-chess.js"), "utf8");
eval(classicCode);

function createTestUI() {
    const mockApp = {
        showToast: () => {},
        hideAllModals: () => {},
        switchView: () => {},
    };
    const ui = new window.ClassicChessUI(mockApp);
    if (ui.clockInterval?.unref) ui.clockInterval.unref();
    else clearInterval(ui.clockInterval);
    return ui;
}

test("Classic Chess SoundSystem Resilience", async (t) => {
    await t.test("SoundSystem has playGameStart and aliases", () => {
        assert.equal(typeof window.soundSystem.playGameStart, "function");
        assert.equal(typeof window.soundSystem.playStart, "function");
        assert.equal(typeof window.soundSystem.playStartMatch, "function");
    });

    await t.test("playGameStart does not throw when AudioContext is absent or uninitialized", () => {
        assert.doesNotThrow(() => {
            window.soundSystem.playGameStart();
            window.soundSystem.playStart();
            window.soundSystem.playMove();
            window.soundSystem.playCapture();
            window.soundSystem.playCheck();
            window.soundSystem.playCheckmate();
            window.soundSystem.playVictory();
        });
    });
});

test("ClassicChessUI safePlaySound Graceful Degradation", async (t) => {
    const ui = createTestUI();

    await t.test("safePlaySound executes existing methods cleanly", () => {
        assert.doesNotThrow(() => {
            ui.safePlaySound("playGameStart");
            ui.safePlaySound("playMove");
        });
    });

    await t.test("safePlaySound fails gracefully on nonexistent methods without throwing", () => {
        assert.doesNotThrow(() => {
            ui.safePlaySound("nonExistentSoundMethod123");
        });
    });

    await t.test("safePlaySound fails gracefully if soundSystem is null or throws", () => {
        const originalSound = window.soundSystem;
        window.soundSystem = {
            playGameStart: () => { throw new Error("AudioContext blocked by autoplay policy"); }
        };
        assert.doesNotThrow(() => {
            ui.safePlaySound("playGameStart");
        });
        window.soundSystem = null;
        assert.doesNotThrow(() => {
            ui.safePlaySound("playGameStart");
        });
        window.soundSystem = originalSound;
    });
});

test("ClassicChessUI Piece Move Logic & State Validation", async (t) => {
    const ui = createTestUI();
    ui.mode = "local";
    ui.mySide = "white";
    ui.roomStatus = "PLAYING";

    ui.state = {
        fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        turn: "white",
        status: "PLAYING",
        moves: [],
        legal_moves: [
            { from: "e2", to: "e3", promotion: null },
            { from: "e2", to: "e4", promotion: null },
            { from: "d2", to: "d4", promotion: null },
        ],
        captured: { white: [], black: [] },
        clocks: { white: 600, black: 600 },
    };

    await t.test("pieceAt locates initial pieces correctly", () => {
        assert.equal(ui.pieceAt("e2"), "P");
        assert.equal(ui.pieceAt("e1"), "K");
        assert.equal(ui.pieceAt("e8"), "k");
        assert.equal(ui.pieceAt("e7"), "p");
        assert.equal(ui.pieceAt("e4"), null);
    });

    await t.test("selectSquare does nothing when status is WAITING", () => {
        let sentMessage = null;
        ui.send = (msg) => { sentMessage = msg; };
        ui.roomStatus = "WAITING";
        ui.state.status = "WAITING";

        ui.selectSquare("e2");
        assert.equal(ui.selectedSquare, null);

        ui.selectSquare("e4");
        assert.equal(sentMessage, null);
    });

    await t.test("selectSquare selects white piece and executes e2 to e4 move", () => {
        let sentMessage = null;
        ui.send = (msg) => { sentMessage = msg; };
        ui.roomStatus = "PLAYING";
        ui.state.status = "PLAYING";
        ui.renderBoard = () => {};

        // Step 1: Select e2
        ui.selectSquare("e2");
        assert.equal(ui.selectedSquare, "e2");

        // Step 2: Target e4
        ui.selectSquare("e4");
        assert.deepEqual(sentMessage, {
            type: "MOVE",
            from: "e2",
            to: "e4",
            promotion: null,
        });
        assert.equal(ui.selectedSquare, null);
    });
});
