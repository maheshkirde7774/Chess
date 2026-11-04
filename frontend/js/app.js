/**
 * Quad Chess / Four Player Grandmaster - Main Application Controller
 * Manages multi-screen navigation, tournament game modes (Online, AI Bots, 2v2 Team, Local),
 * WebSocket synchronization, tactical puzzles, leaderboards, themes, and sound FX.
 */

class QuadChessApp {
    constructor() {
        this.engine = new window.ClientChessEngine();
        this.ai = new window.FourPlayerAI("club");
        this.gameMode = "local"; // "local", "ai", "team", "online", "puzzle"
        this.aiDifficulty = "club";
        this.activePuzzle = null;

        this.isOnlineMode = false;
        this.roomCode = null;
        this.playerId = null;
        this.myRole = null; // 1: Cyan, 2: Magenta, 3: Lime, 4: Gold
        this.onlinePlayers = {};
        this.roomSettings = {};
        this.spectatorToken = null;
        this.lobbyReady = false;

        this.wsClient = new window.WebSocketClient(
            (msg) => this.handleServerMessage(msg),
            (status) => this.handleConnectionStatus(status)
        );

        this.ui = new window.ChessUI(this.engine, (move, isCapture) => this.onPlayerMove(move, isCapture));
        this.classicChess = new window.ClassicChessUI(this);
        this.dailyPuzzles = new window.DailyPuzzleUI(this);

        this.aiSelectedMode = "four_player";
        this.currentView = "view-home";
        this.social = new window.FOURXSocialController(this);
        this.spectator = new window.SpectatorController(this);
        this.initEventListeners();
        this.initSettingsValues();
        this.initDashboardData();
        this.initPuzzlesList();
        this.initLeaderboardData();
        this.restoreFourPlayerSession();
        const urlParams = new URLSearchParams(window.location.search);
        const previewW = urlParams.get("preview_w") || ((urlParams.get("preview_mobile") === "1" || urlParams.get("mobile") === "1") ? "390" : null);
        if (previewW) {
            const root = document.getElementById("app-root");
            if (root) {
                root.style.maxWidth = `${previewW}px`;
                root.style.width = `${previewW}px`;
                root.style.margin = "0";
            }
        }
        if (urlParams.get("view") === "classic" || urlParams.get("preview") === "classic") {
            const runInit = () => {
                this.switchView("view-classic");
                this.classicChess.roomCode = "TEST12";
                this.classicChess.playerId = "player1";
                this.classicChess.humanSide = "white";
                this.classicChess.mySide = "white";
                this.classicChess.mode = "ai";
                this.classicChess.ai = { ai_side: "black" };
                this.classicChess.state = {
                    fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                    moves: [
                        { uci: "e2e4", san: "e4" },
                        { uci: "e7e5", san: "e5" },
                        { uci: "g1f3", san: "Nf3" },
                        { uci: "b8c6", san: "Nc6" },
                        { uci: "f1c4", san: "Bc4" },
                        { uci: "g8f6", san: "Nf6" }
                    ],
                    turn: "white",
                    legal_moves: [{ from: "d2", to: "d4" }],
                    in_check: false,
                    draw_offer: null,
                    can_claim_draw: false,
                    last_mover: "black",
                    captured: { white: ["p"], black: ["p"] },
                    clocks: { white: 582, black: 591 }
                };
                this.classicChess.players = {
                    white: { name: "Player 1", rating: 1200 },
                    black: { name: "Commander AI (1400)", rating: 1400 }
                };
                this.classicChess.roomStatus = "PLAYING";
                const mockData = {
                    room_code: "TEST12",
                    status: "PLAYING",
                    human_side: "white",
                    state: this.classicChess.state,
                    players: this.classicChess.players,
                    ai: { ai_side: "black" }
                };
                this.classicChess.enterRoom(mockData, "ai");
            };
            runInit();
        }
    }

    /* ==================== VIEW NAVIGATION ==================== */

    switchView(viewId) {
        if (this.currentView === "view-live-games" && viewId !== "view-live-games") {
            this.spectator?.onLobbyExited();
        }
        if (this.currentView === "view-spectator" && viewId !== "view-spectator") {
            this.spectator?.onSpectatorExited();
        }
        document.querySelectorAll(".app-view").forEach(v => v.classList.remove("active-view"));
        const targetView = document.getElementById(viewId);
        if (targetView) {
            targetView.classList.add("active-view");
            this.currentView = viewId;
        }
        if (viewId === "view-puzzles") this.dailyPuzzles?.onViewEntered();
        if (viewId === "view-live-games") this.spectator?.onLobbyEntered();
        if (viewId === "view-customization") window.FOURXCustomization?.onOpen();
        if (viewId === "view-membership") window.FOURXSubscription?.onOpen();
        window.FOURXAds?.refresh();

        // Update Bottom Nav active state
        document.querySelectorAll(".nav-tab-btn").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.target === viewId);
        });

        // Header adaptations & App Root in-game view toggle
        const appRoot = document.getElementById("app-root");
        const backBtn = document.getElementById("btn-back-home");
        const turnBadge = document.getElementById("turn-badge");
        const roomCodeTag = document.getElementById("room-code-tag");

        if (viewId === "view-game" || viewId === "view-classic") {
            appRoot?.classList.add("in-game-view");
            if (viewId === "view-game") {
                backBtn?.classList.remove("hidden");
                turnBadge?.classList.remove("hidden");
                if (this.isOnlineMode) roomCodeTag?.classList.remove("hidden");
                // Dynamically resize chessboard to maximum available arena dimensions
                setTimeout(() => this.ui?.resizeBoard?.(), 40);
            } else {
                backBtn?.classList.add("hidden");
                turnBadge?.classList.add("hidden");
                roomCodeTag?.classList.add("hidden");
            }
        } else {
            appRoot?.classList.remove("in-game-view");
            if (viewId === "view-membership") {
                backBtn?.classList.remove("hidden");
            } else {
                backBtn?.classList.add("hidden");
            }
            turnBadge?.classList.add("hidden");
            roomCodeTag?.classList.add("hidden");
        }

        if (viewId === "view-profile") window.FOURXProfile?.refresh();
        if (viewId === "view-friends") this.social?.onViewEntered();
        window.soundSystem.playClick();
    }

    /* ==================== EVENT LISTENERS ==================== */

    initEventListeners() {
        // Bottom Navigation Tabs
        document.querySelectorAll(".nav-tab-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const target = e.currentTarget.dataset.target;
                if (target) this.switchView(target);
            });
        });

        // Top Navigation Back Button
        document.getElementById("btn-back-home")?.addEventListener("click", () => {
            this.switchView("view-home");
        });
        document.getElementById("btn-membership-back")?.addEventListener("click", () => {
            this.switchView("view-home");
        });

        // Brand Logo click -> Home
        document.getElementById("nav-brand-logo")?.addEventListener("click", () => {
            this.switchView("view-home");
        });

        // Header Action Buttons
        document.getElementById("btn-membership-header")?.addEventListener("click", () => {
            this.switchView("view-membership");
        });
        document.getElementById("btn-nav-rules")?.addEventListener("click", () => this.showModal("rules-modal"));
        document.getElementById("btn-nav-settings")?.addEventListener("click", () => {
            this.switchView("view-customization");
        });
        document.getElementById("btn-sound-toggle")?.addEventListener("click", () => {
            const isMuted = window.soundSystem.toggleMute();
            this.updateSoundIcon(!isMuted);
        });

        // 7 Home Screen Main Menu Options
        document.getElementById("menu-item-play-4p")?.addEventListener("click", () => {
            this.showModal("menu-modal");
        });
        document.getElementById("menu-item-classic-1v1")?.addEventListener("click", () => {
            this.showModal("classic-menu-modal");
        });
        document.getElementById("menu-item-live-games")?.addEventListener("click", () => {
            this.switchView("view-live-games");
        });
        document.getElementById("menu-item-friends")?.addEventListener("click", () => {
            this.switchView("view-friends");
        });
        document.getElementById("menu-item-ai")?.addEventListener("click", () => {
            this.updateAiModalUI();
            this.showModal("ai-modal");
        });
        document.getElementById("menu-item-puzzles")?.addEventListener("click", () => {
            this.showModal("learn-modal");
        });
        document.getElementById("menu-item-profile")?.addEventListener("click", () => {
            this.switchView("view-profile");
        });
        document.getElementById("menu-item-settings")?.addEventListener("click", () => {
            this.switchView("view-customization");
        });

        // Quick Play Hero Banner & Legacy Card Fallbacks
        document.getElementById("btn-quick-play")?.addEventListener("click", () => {
            this.startAIGame("club");
        });
        document.getElementById("card-mode-online")?.addEventListener("click", () => {
            this.showModal("menu-modal");
        });
        document.getElementById("card-mode-ai")?.addEventListener("click", () => {
            this.showModal("ai-modal");
        });
        document.getElementById("card-mode-team")?.addEventListener("click", () => {
            this.startTeamGame();
        });
        document.getElementById("card-mode-local")?.addEventListener("click", () => {
            this.startLocalGame();
        });

        // Daily Puzzle Button
        document.getElementById("btn-start-daily-puzzle")?.addEventListener("click", () => {
            this.switchView("view-puzzles");
        });

        // AI Modal Mode Selector (Four-Player vs Classic 1v1)
        document.querySelectorAll(".ai-mode-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                document.querySelectorAll(".ai-mode-btn").forEach(b => {
                    b.classList.remove("active");
                    b.setAttribute("aria-checked", "false");
                });
                const target = e.currentTarget;
                target.classList.add("active");
                target.setAttribute("aria-checked", "true");
                this.aiSelectedMode = target.dataset.mode || "four_player";
                this.updateAiModalUI();
            });
        });

        // AI Modal Diff Buttons
        document.querySelectorAll(".ai-diff-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                document.querySelectorAll(".ai-diff-btn").forEach(b => b.classList.remove("active"));
                e.currentTarget.classList.add("active");
                this.aiDifficulty = e.currentTarget.dataset.diff || "club";
            });
        });

        document.getElementById("btn-start-ai-match")?.addEventListener("click", () => {
            this.hideAllModals();
            const mode = this.aiSelectedMode || "four_player";
            const diff = this.aiDifficulty || "club";
            if (mode === "classic") {
                this.startClassicAIMatch(diff);
            } else {
                this.startAIGame(diff);
            }
        });

        // In-Game Reactions Popover Bar
        document.getElementById("btn-toggle-reactions")?.addEventListener("click", () => {
            const bar = document.getElementById("arena-reactions-bar");
            bar?.classList.toggle("hidden");
        });

        document.querySelectorAll(".arena-reactions-bar .emote-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const text = e.currentTarget.dataset.text || e.currentTarget.textContent;
                this.showToast(`Sent: ${text}`);
                window.soundSystem?.playClick();
                if (this.isOnlineMode && this.wsClient) {
                    this.wsClient.sendChat(text);
                }
                document.getElementById("arena-reactions-bar")?.classList.add("hidden");
            });
        });

        // Notation Drawer / Sidebar Toggle
        document.getElementById("btn-toggle-notation")?.addEventListener("click", () => {
            const drawer = document.getElementById("notation-drawer");
            drawer?.classList.toggle("hidden");
            setTimeout(() => this.ui?.resizeBoard?.(), 50);
        });
        document.getElementById("btn-close-notation")?.addEventListener("click", () => {
            document.getElementById("notation-drawer")?.classList.add("hidden");
            setTimeout(() => this.ui?.resizeBoard?.(), 50);
        });

        // Game Controls
        document.getElementById("btn-undo")?.addEventListener("click", () => this.handleUndo());
        document.getElementById("btn-restart")?.addEventListener("click", () => this.handleRestart());
        document.getElementById("btn-resign")?.addEventListener("click", () => this.handleResign());
        document.getElementById("btn-rotate")?.addEventListener("click", () => this.ui.manualRotate());

        // Mode Selection Modal Buttons
        document.getElementById("btn-mode-local")?.addEventListener("click", () => {
            this.hideAllModals();
            this.startLocalGame();
        });
        document.getElementById("btn-mode-team-modal")?.addEventListener("click", () => {
            this.hideAllModals();
            this.startTeamGame();
        });
        document.getElementById("btn-mode-create")?.addEventListener("click", () => {
            this.hideAllModals();
            this.showModal("create-room-modal");
        });
        document.getElementById("btn-mode-join")?.addEventListener("click", () => {
            this.hideAllModals();
            this.showModal("join-room-modal");
        });

        // Learn & Puzzles Modal Actions
        document.getElementById("btn-learn-puzzles")?.addEventListener("click", () => {
            this.hideAllModals();
            this.switchView("view-puzzles");
        });
        document.getElementById("btn-learn-rules")?.addEventListener("click", () => {
            this.hideAllModals();
            this.showModal("rules-modal");
        });

        // Forms: Create / Join Room
        document.getElementById("form-create-room")?.addEventListener("submit", (e) => {
            e.preventDefault();
            const nameInput = document.getElementById("create-player-name");
            const name = nameInput ? nameInput.value.trim() : "Grandmaster";
            const mode = document.getElementById("create-game-mode")?.value || "four_player";
            const timeControl = document.getElementById("create-time-control")?.value || "unlimited";
            if (mode === "classic") {
                this.classicChess.createOnlineRoom(
                    name,
                    timeControl,
                    document.getElementById("create-room-private")?.checked !== false
                );
            } else {
                this.createOnlineRoom(name, {
                    is_private: document.getElementById("create-room-private")?.checked !== false,
                    time_control: timeControl,
                });
            }
        });

        document.getElementById("form-join-room")?.addEventListener("submit", (e) => {
            e.preventDefault();
            const codeInput = document.getElementById("join-room-code");
            const nameInput = document.getElementById("join-player-name");
            const code = codeInput ? codeInput.value.trim().toUpperCase() : "";
            const name = nameInput ? nameInput.value.trim() : "Guest";
            if (code) this.joinOnlineRoom(code, name);
        });
        document.getElementById("btn-browse-public-rooms")?.addEventListener("click", () => {
            this.loadPublicRooms();
        });

        // Copy Room Code
        document.getElementById("btn-copy-code")?.addEventListener("click", () => {
            if (this.roomCode) {
                navigator.clipboard.writeText(this.roomCode).then(() => {
                    this.showToast(`Room Code ${this.roomCode} copied!`);
                }).catch(() => {
                    this.showToast(`Code: ${this.roomCode}`);
                });
            }
        });
        document.getElementById("btn-lobby-copy")?.addEventListener("click", () => this.copyRoomCode());
        document.getElementById("btn-lobby-share")?.addEventListener("click", () => this.shareRoomInvite());
        document.getElementById("btn-copy-spectator-key")?.addEventListener("click", () => this.copySpectatorKey());
        document.getElementById("btn-lobby-ready")?.addEventListener("click", () => {
            this.lobbyReady = !this.lobbyReady;
            this.wsClient.send({ type: "READY", ready: this.lobbyReady });
        });
        document.getElementById("btn-lobby-start")?.addEventListener("click", () => {
            this.wsClient.send({ type: "START_GAME" });
        });
        document.getElementById("btn-lobby-leave")?.addEventListener("click", () => this.leaveRoom());

        // Pass Device Privacy Screen
        document.getElementById("btn-pass-unlock")?.addEventListener("click", () => {
            document.getElementById("pass-device-modal")?.classList.add("hidden");
        });

        // Game Over Buttons
        document.getElementById("btn-play-again")?.addEventListener("click", () => {
            this.hideAllModals();
            this.handleRestart();
        });
        document.getElementById("btn-gameover-menu")?.addEventListener("click", () => {
            this.hideAllModals();
            this.switchView("view-home");
        });

        // Modal Close Buttons
        document.querySelectorAll(".modal-close-btn, .modal-close-action-btn").forEach(btn => {
            btn.addEventListener("click", () => this.hideAllModals());
        });

        // Chat Emotes
        document.querySelectorAll(".emote-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const text = e.currentTarget.dataset.text || e.currentTarget.textContent;
                this.sendChatMessage(text);
            });
        });

        // Settings Actions
        document.getElementById("btn-save-settings")?.addEventListener("click", () => {
            const urlInput = document.getElementById("backend-url-input");
            if (urlInput && urlInput.value) {
                window.CONFIG.setServerUrl(urlInput.value);
            }
            const soundToggle = document.getElementById("sound-toggle-chk");
            if (soundToggle) {
                window.soundSystem.applyPreferences({
                    ...window.soundSystem.preferences,
                    enabled: soundToggle.checked,
                });
                window.FOURXCustomization?.onSoundEnabledChanged(soundToggle.checked);
                this.updateSoundIcon(soundToggle.checked);
            }
            const passToggle = document.getElementById("pass-prompt-chk");
            if (passToggle) window.CONFIG.setPassPromptEnabled(passToggle.checked);

            const rotateToggle = document.getElementById("rotate-board-chk");
            if (rotateToggle) window.CONFIG.setAutoRotateEnabled(rotateToggle.checked);

            this.showToast("Preferences saved.");
            this.hideAllModals();
        });

        document.getElementById("btn-test-backend")?.addEventListener("click", () => this.testBackendConnection());

        document.getElementById("btn-open-customization")?.addEventListener("click", () => {
            this.switchView("view-customization");
        });
        document.getElementById("link-upgrade-adfree")?.addEventListener("click", (e) => {
            e.preventDefault();
            this.switchView("view-membership");
        });
    }

    initSettingsValues() {
        const urlInput = document.getElementById("backend-url-input");
        if (urlInput) urlInput.value = window.CONFIG.getServerUrl();

        const soundToggle = document.getElementById("sound-toggle-chk");
        if (soundToggle) soundToggle.checked = window.CONFIG.isAudioEnabled();

        const passToggle = document.getElementById("pass-prompt-chk");
        if (passToggle) passToggle.checked = window.CONFIG.isPassPromptEnabled();

        const rotateToggle = document.getElementById("rotate-board-chk");
        if (rotateToggle) rotateToggle.checked = window.CONFIG.isAutoRotateEnabled();
    }

    /* ==================== GAME MODES ==================== */

    startLocalGame() {
        this.gameMode = "local";
        this.isOnlineMode = false;
        this.roomCode = null;
        this.playerId = null;
        this.myRole = null;
        this.wsClient.disconnect();

        document.getElementById("arena-mode-label").textContent = "Pass & Play (Local)";
        document.getElementById("btn-undo")?.classList.remove("hidden");

        this.engine = new window.ClientChessEngine();
        this.ui.engine = this.engine;
        this.ui.clocks = { 1: 600, 2: 600, 3: 600, 4: 600 };
        this.ui.render();

        this.switchView("view-game");
        window.soundSystem.playGameStart();
        this.showToast("Pass & Play Match Initialized");
    }

    updateAiModalUI() {
        const isClassic = this.aiSelectedMode === "classic";
        const diffLabel = document.getElementById("ai-diff-label");
        const startBtn = document.getElementById("btn-start-ai-match");
        const subNovice = document.getElementById("ai-diff-sub-novice");
        const subClub = document.getElementById("ai-diff-sub-club");
        const subMaster = document.getElementById("ai-diff-sub-master");

        if (diffLabel) {
            diffLabel.textContent = isClassic 
                ? "ENGINE SEARCH DEPTH FOR 1V1 OPPONENT" 
                : "TACTICAL DIFFICULTY FOR 3 AI RIVALS";
        }
        if (startBtn) {
            startBtn.textContent = isClassic 
                ? "Start Classic 1v1 Match" 
                : "Start 4-Player AI Match";
        }
        if (subNovice) {
            subNovice.textContent = isClassic 
                ? "Relaxed search, occasional tactical concessions" 
                : "Relaxed casual play, ideal for practice";
        }
        if (subClub) {
            subClub.textContent = isClassic 
                ? "Balanced search with piece valuation & positional play" 
                : "Balanced positional play & tactics";
        }
        if (subMaster) {
            subMaster.textContent = isClassic 
                ? "Deep iterative search, tactical calculations & defense" 
                : "Deep search, checks & aggressive defense";
        }
    }

    async startClassicAIMatch(difficulty = "club") {
        const diffMap = {
            "novice": "beginner",
            "club": "intermediate",
            "master": "advanced"
        };
        const mappedDiff = diffMap[difficulty] || difficulty || "intermediate";
        if (this.classicChess) {
            await this.classicChess.startAiGame(mappedDiff, "white", "10+0");
        }
    }

    startAIGame(difficulty = "club") {
        this.gameMode = "ai";
        this.aiDifficulty = difficulty;
        this.ai.setDifficulty(difficulty);
        this.isOnlineMode = false;
        this.roomCode = null;
        this.playerId = null;
        this.myRole = 1; // Human is Cyan (South)
        this.wsClient.disconnect();

        const diffLabels = { novice: "Novice (800)", club: "Club (1400)", master: "Master (2000)" };
        document.getElementById("arena-mode-label").textContent = `Play vs AI: ${diffLabels[difficulty] || difficulty}`;
        document.getElementById("btn-undo")?.classList.remove("hidden");

        // Update Bot names in HUD
        const botNames = { 2: "DeepBot (West)", 3: "StockBot (North)", 4: "Tactix (East)" };
        for (let p = 2; p <= 4; p++) {
            const card = document.getElementById(`player-card-${p}`);
            const nameEl = card?.querySelector(".player-name");
            if (nameEl) nameEl.textContent = botNames[p];
        }

        this.engine = new window.ClientChessEngine();
        this.ui.engine = this.engine;
        this.ui.clocks = { 1: 600, 2: 600, 3: 600, 4: 600 };
        this.ui.render();

        this.switchView("view-game");
        window.soundSystem.playGameStart();
        this.showToast(`AI Match Started (${diffLabels[difficulty]})`);
    }

    startTeamGame() {
        this.gameMode = "team";
        this.aiDifficulty = "club";
        this.ai.setDifficulty("club");
        this.isOnlineMode = false;
        this.roomCode = null;
        this.playerId = null;
        this.myRole = 1;
        this.wsClient.disconnect();

        document.getElementById("arena-mode-label").textContent = "2v2 Alliance: Cyan & Lime vs Rivals";
        document.getElementById("btn-undo")?.classList.remove("hidden");

        this.engine = new window.ClientChessEngine();
        this.ui.engine = this.engine;
        this.ui.clocks = { 1: 600, 2: 600, 3: 600, 4: 600 };
        this.ui.render();

        this.switchView("view-game");
        window.soundSystem.playGameStart();
        this.showToast("2v2 Team Battle Initialized! Ally: Lime (North)");
    }

    startPuzzle(puzzle) {
        this.gameMode = "puzzle";
        this.activePuzzle = puzzle;
        this.isOnlineMode = false;
        this.myRole = puzzle.player;

        document.getElementById("arena-mode-label").textContent = `Puzzle: ${puzzle.title} (${puzzle.rating} Elo)`;
        document.getElementById("btn-undo")?.classList.add("hidden");

        this.engine = new window.ClientChessEngine();
        this.ui.engine = this.engine;
        this.ui.render();

        this.switchView("view-game");
        window.soundSystem.playGameStart();
        this.showToast(`Tactical Challenge: ${puzzle.description}`);
    }

    /* ==================== ONLINE MULTIPLAYER ==================== */

    async createOnlineRoom(playerName, settings = {}) {
        try {
            await window.FOURXProfile.ready;
            this.showToast("Creating Tournament Arena...");
            const serverUrl = window.CONFIG.getServerUrl();
            const res = await fetch(`${serverUrl}/rooms`, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...window.FOURXProfile.authHeaders() },
                body: JSON.stringify({ player_name: playerName, ...settings })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Failed to create room");
            }

            const data = await res.json();
            this.roomCode = data.room_code;
            this.playerId = data.player_id;
            this.spectatorToken = data.spectator_token || null;
            this.myRole = data.player_role;
            this.isOnlineMode = true;
            this.gameMode = "online";

            this.hideAllModals();
            this.roomSettings = settings;
            this.lobbyReady = true;
            this.saveFourPlayerSession();
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);

            this.switchView("view-room-lobby");
            this.renderRoomLobby();
            this.showToast(`Room ${this.roomCode} created! Share code with friends.`);
        } catch (e) {
            console.error("Room creation error:", e);
            this.showToast(`Error: ${e.message}`, true);
        }
    }

    async loadPublicRooms() {
        const container = document.getElementById("public-room-list");
        if (!container) return;
        container.textContent = "Loading public rooms…";
        try {
            const response = await fetch(`${window.CONFIG.getServerUrl()}/rooms`);
            const rooms = await response.json();
            if (!response.ok) throw new Error(rooms.detail || "Could not load public rooms.");
            container.replaceChildren();
            if (rooms.length === 0) {
                container.textContent = "No public rooms are waiting right now.";
                return;
            }
            rooms.forEach((room) => {
                const row = document.createElement("div");
                row.className = "public-room-entry";
                const description = document.createElement("span");
                const capacity = room.settings.max_players;
                description.textContent = `${room.room_code} · ${Object.keys(room.players).length}/${capacity} players · ${room.settings.game_mode === "classic" ? "Classic" : "Four-Player"}`;
                const join = document.createElement("button");
                join.className = "neon-btn secondary-btn";
                join.textContent = "Join";
                join.addEventListener("click", () => {
                    const name = document.getElementById("join-player-name")?.value.trim() || "Guest";
                    if (room.settings.game_mode === "classic") {
                        this.classicChess.joinRoomWithCode(room.room_code, name);
                    } else {
                        this.joinOnlineRoom(room.room_code, name);
                    }
                });
                row.append(description, join);
                container.append(row);
            });
        } catch (error) {
            container.textContent = error.message;
        }
    }

    async joinOnlineRoom(roomCode, playerName) {
        try {
            await window.FOURXProfile.ready;
            this.showToast(`Connecting to room ${roomCode}...`);
            const serverUrl = window.CONFIG.getServerUrl();
            const res = await fetch(`${serverUrl}/rooms/join`, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...window.FOURXProfile.authHeaders() },
                body: JSON.stringify({ room_code: roomCode, player_name: playerName })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Failed to join room");
            }

            const data = await res.json();
            this.roomCode = data.room_code;
            this.playerId = data.player_id;
            this.spectatorToken = data.spectator_token || null;
            this.myRole = data.player_role;
            this.isOnlineMode = true;
            this.gameMode = "online";

            this.hideAllModals();
            this.lobbyReady = false;
            this.saveFourPlayerSession();
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);

            this.switchView("view-room-lobby");
            this.renderRoomLobby();
            this.showToast(`Joined as ${window.PLAYER_INFO[this.myRole]?.name || 'Player'}!`);
        } catch (e) {
            console.error("Room join error:", e);
            this.showToast(`Error: ${e.message}`, true);
        }
    }

    async joinSocialInvitation(launch) {
        if (!launch?.room_code || !launch?.player_id) {
            this.showToast("This invitation does not contain valid room access.", true);
            return;
        }
        try {
            if (launch.game_mode === "classic") {
                let roomState = launch;
                if (!launch.game_state) {
                    const response = await fetch(
                        `${window.CONFIG.getServerUrl()}/classic/rooms/${encodeURIComponent(launch.room_code)}`,
                        { headers: { Authorization: `Bearer ${launch.player_id}` } }
                    );
                    roomState = await response.json();
                    if (!response.ok) throw new Error(roomState.detail || "Could not load invited match.");
                }
                this.classicChess.enterRoom(
                    {
                        ...roomState,
                        player_id: launch.player_id,
                        spectator_token: launch.spectator_token || null,
                    },
                    "online"
                );
                return;
            }
            if (launch.game_mode !== "four_player") {
                throw new Error("Unsupported invited game mode.");
            }
            this.roomCode = launch.room_code;
            this.playerId = launch.player_id;
            this.myRole = launch.player_role;
            this.isOnlineMode = true;
            this.gameMode = "online";
            this.roomSettings = {
                game_mode: "four_player",
                is_private: true,
                time_control: "unlimited",
                max_players: 4,
            };
            this.lobbyReady = false;
            this.hideAllModals();
            this.saveFourPlayerSession();
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);
            this.switchView("view-room-lobby");
            this.renderRoomLobby();
        } catch (error) {
            this.showToast(`Could not join invited match: ${error.message}`, true);
        }
    }

    setupOnlineUI() {
        const roomTag = document.getElementById("room-code-tag");
        const roomCodeText = document.getElementById("current-room-code");
        if (roomTag && roomCodeText) {
            roomTag.classList.remove("hidden");
            roomCodeText.textContent = this.roomCode;
        }

        document.getElementById("network-indicator")?.classList.remove("hidden");
        document.getElementById("btn-undo")?.classList.add("hidden");
        document.getElementById("arena-mode-label").textContent = `Online Arena: #${this.roomCode}`;
    }

    saveFourPlayerSession() {
        sessionStorage.setItem("fourPlayerChessSession", JSON.stringify({
            roomCode: this.roomCode,
            playerId: this.playerId,
            playerRole: this.myRole,
            spectatorToken: this.spectatorToken,
        }));
    }

    async restoreFourPlayerSession() {
        let saved;
        try {
            saved = JSON.parse(sessionStorage.getItem("fourPlayerChessSession") || "null");
        } catch (error) {
            sessionStorage.removeItem("fourPlayerChessSession");
            return;
        }
        if (!saved?.roomCode || !saved?.playerId) return;
        try {
            const response = await fetch(
                `${window.CONFIG.getServerUrl()}/rooms/${encodeURIComponent(saved.roomCode)}`
            );
            if (!response.ok) throw new Error("Saved room is no longer available.");
            const room = await response.json();
            this.roomCode = room.room_code;
            this.playerId = saved.playerId;
            this.spectatorToken = saved.spectatorToken || null;
            this.myRole = saved.playerRole || this.myRole;
            this.roomSettings = room.settings || {};
            this.isOnlineMode = true;
            this.gameMode = "online";
            this.onlinePlayers = room.players || {};
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);
            this.switchView(room.status === "PLAYING" || room.status === "COMPLETED" ? "view-game" : "view-room-lobby");
            this.renderRoomLobby(room);
        } catch (error) {
            sessionStorage.removeItem("fourPlayerChessSession");
            this.showToast(error.message, true);
        }
    }

    renderRoomLobby(state = null) {
        const code = document.getElementById("lobby-room-code");
        const slots = document.getElementById("lobby-player-slots");
        if (!code || !slots || !this.roomCode) return;
        code.textContent = this.roomCode;
        const spectatorInvite = document.getElementById("lobby-spectator-invite");
        const spectatorKey = document.getElementById("lobby-spectator-key");
        spectatorInvite?.classList.toggle("hidden", !this.spectatorToken);
        if (spectatorKey) spectatorKey.value = this.spectatorToken || "";
        const players = state?.players || this.onlinePlayers || {};
        const hostRole = state?.host_role || Object.keys(players).find(
            (role) => players[role]?.host
        );
        const status = state?.status || "WAITING";
        const statusText = document.getElementById("lobby-status-text");
        const playerCount = Object.keys(players).length;
        if (statusText) {
            statusText.textContent = status === "PLAYING"
                ? "The host has started the match."
                : `${playerCount} of 4 seats filled · ${this.roomSettings.is_private === false ? "Public room" : "Private room"}`;
        }
        slots.replaceChildren();
        for (let role = 1; role <= 4; role += 1) {
            const player = players[String(role)] || players[role];
            const slot = document.createElement("div");
            slot.className = `lobby-player-slot${player ? " occupied" : ""}`;
            const seat = document.createElement("strong");
            seat.textContent = window.PLAYER_INFO[role]?.name || `Seat ${role}`;
            const name = document.createElement("span");
            name.textContent = player?.name || "Open seat";
            const details = document.createElement("small");
            details.textContent = player
                ? `${player.host ? "Host · " : ""}${player.connected ? "Online" : "Reconnecting"} · ${player.ready ? "Ready" : "Not ready"}`
                : "Waiting for a player";
            slot.append(seat, name, details);
            slots.append(slot);
        }
        const readyButton = document.getElementById("btn-lobby-ready");
        const startButton = document.getElementById("btn-lobby-start");
        if (readyButton) {
            readyButton.classList.toggle("hidden", Number(this.myRole) === Number(hostRole) || status !== "WAITING");
            readyButton.textContent = this.lobbyReady ? "Cancel Ready" : "Ready";
        }
        if (startButton) {
            startButton.classList.toggle("hidden", Number(this.myRole) !== Number(hostRole) || status !== "WAITING");
            startButton.disabled = playerCount !== 4;
            startButton.title = playerCount === 4 ? "" : "All four seats must be filled";
        }
    }

    async copyRoomCode() {
        if (!this.roomCode) return;
        try {
            await navigator.clipboard.writeText(this.roomCode);
            this.showToast("Room code copied.");
        } catch (error) {
            this.showToast(`Share room code: ${this.roomCode}`);
        }
    }

    async shareRoomInvite() {
        if (!this.roomCode) return;
        const invitation = {
            title: "FOURX room invitation",
            text: `Join my FOURX chess room. Room code: ${this.roomCode}${this.spectatorToken ? ` · Private spectator key: ${this.spectatorToken}` : ""}`,
            url: window.location.href,
        };
        try {
            if (navigator.share) await navigator.share(invitation);
            else await this.copyRoomCode();
        } catch (error) {
            if (error.name !== "AbortError") {
                this.showToast(`Room code: ${this.roomCode}${this.spectatorToken ? ` · Spectator key: ${this.spectatorToken}` : ""}`);
            }
        }
    }

    async copySpectatorKey() {
        if (!this.spectatorToken) return;
        try {
            await navigator.clipboard.writeText(this.spectatorToken);
            this.showToast("Private spectator key copied.");
        } catch (error) {
            this.showToast(`Private spectator key: ${this.spectatorToken}`);
        }
    }

    async leaveRoom() {
        if (!this.roomCode || !this.playerId) return;
        try {
            const response = await fetch(
                `${window.CONFIG.getServerUrl()}/rooms/${encodeURIComponent(this.roomCode)}/leave`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ player_id: this.playerId }),
                }
            );
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Could not leave room.");
            this.wsClient.disconnect();
            sessionStorage.removeItem("fourPlayerChessSession");
            this.roomCode = null;
            this.playerId = null;
            this.myRole = null;
            this.isOnlineMode = false;
            this.switchView("view-home");
        } catch (error) {
            this.showToast(error.message, true);
        }
    }

    /* ==================== MOVE HANDLING & AI BOTS ==================== */

    onPlayerMove(move, isCapture) {
        if (this.gameMode === "puzzle" && this.activePuzzle) {
            // Check puzzle solution
            const sol = this.activePuzzle.solution;
            if (move.from[0] === sol.from[0] && move.from[1] === sol.from[1] &&
                move.to[0] === sol.to[0] && move.to[1] === sol.to[1]) {
                const res = this.engine.makeMove(move);
                if (isCapture) window.soundSystem.playCapture();
                else window.soundSystem.playMove();
                this.ui.render();
                this.showToast(`✓ Brilliant! Puzzle Solved (+16 Rating)`);
                window.soundSystem.playVictory();
                return;
            } else {
                this.showToast(`✗ Incorrect move. Try again or check hint!`, true);
                return;
            }
        }

        if (!this.isOnlineMode) {
            // Local / AI / Team Mode
            const res = this.engine.makeMove(move);
            if (res.success) {
                if (isCapture) window.soundSystem.playCapture();
                else window.soundSystem.playMove();

                if (this.engine.isInCheck(this.engine.currentTurn)) {
                    window.soundSystem.playCheck();
                }

                this.ui.render();

                // Pass device prompt in local mode
                if (this.gameMode === "local" && window.CONFIG.isPassPromptEnabled() && !this.engine.isGameOver) {
                    this.showPassDevicePrompt(this.engine.currentTurn);
                }

                // AI Bots execution
                if ((this.gameMode === "ai" || this.gameMode === "team") && !this.engine.isGameOver) {
                    this.checkAndTriggerAIMove();
                }
            } else {
                this.showToast(res.message, true);
            }
        } else {
            // Online Mode
            if (this.myRole !== this.engine.currentTurn) {
                this.showToast("It is not your turn!", true);
                return;
            }

            this.wsClient.send({
                type: "MOVE",
                from: move.from,
                to: move.to,
                promotion: move.promotion || null
            });
        }
    }

    checkAndTriggerAIMove() {
        const curTurn = this.engine.currentTurn;
        // In AI/Team mode, Human is Player 1. If it's Player 2, 3, or 4's turn, trigger bot!
        if (curTurn !== 1 && !this.engine.isGameOver) {
            setTimeout(() => {
                if (this.engine.currentTurn !== curTurn || this.engine.isGameOver) return;
                const is2v2 = (this.gameMode === "team");
                const aiMove = this.ai.chooseMove(this.engine, curTurn, is2v2);
                if (aiMove) {
                    const target = this.engine.getPiece(aiMove.to[0], aiMove.to[1]);
                    const isCap = target !== null;
                    this.ui.animateAndExecuteMove(aiMove, isCap);
                }
            }, 600);
        }
    }

    /* ==================== WEBSOCKET DISPATCH ==================== */

    handleServerMessage(data) {
        if (data.type === "SYNC_STATE") {
            if (data.your_role) this.myRole = data.your_role;
            if (data.settings) this.roomSettings = data.settings;
            if (data.players) {
                this.onlinePlayers = data.players;
                this.lobbyReady = data.players[String(this.myRole)]?.ready === true;
                this.updatePlayersHUD(data.players);
            }
            this.renderRoomLobby(data);
            if (data.game_state) this.ui.render(data.game_state);
            if (data.status === "PLAYING") this.switchView("view-game");
        } else if (data.type === "MOVE_MADE") {
            const isCapture = data.game_state.captured_pieces[data.player]?.length > 
                              this.engine.capturedPieces[data.player]?.length;

            if (isCapture) window.soundSystem.playCapture();
            else window.soundSystem.playMove();

            this.ui.render(data.game_state);

            if (this.engine.isInCheck(this.engine.currentTurn)) {
                window.soundSystem.playCheck();
            }
        } else if (data.type === "PLAYER_JOINED" || data.type === "PRESENCE_UPDATE") {
            if (data.players) {
                this.onlinePlayers = data.players;
                this.lobbyReady = data.players[String(this.myRole)]?.ready === true;
                this.updatePlayersHUD(data.players);
                this.renderRoomLobby({ players: data.players, status: "WAITING" });
            }
            if (data.name) this.showToast(`${data.name} entered the arena`);
        } else if (data.type === "GAME_STARTED") {
            this.onlinePlayers = data.players || this.onlinePlayers;
            if (data.game_state) this.ui.render(data.game_state);
            this.renderRoomLobby({ players: this.onlinePlayers, status: "PLAYING" });
            this.switchView("view-game");
            window.soundSystem.playGameStart();
            this.showToast("The match has started.");
        } else if (data.type === "PLAYER_LEFT") {
            this.onlinePlayers = data.players || {};
            this.renderRoomLobby({ players: this.onlinePlayers, status: "WAITING" });
        } else if (data.type === "PLAYER_RESIGNED") {
            this.showToast(`Player ${data.player} resigned.`);
            if (data.game_state) this.ui.render(data.game_state);
        } else if (data.type === "GAME_RESET") {
            this.showToast("Room reset. Waiting for the host to start.");
            if (data.game_state) this.ui.render(data.game_state);
            this.switchView("view-room-lobby");
            this.onlinePlayers = data.players || this.onlinePlayers;
            this.renderRoomLobby({ players: this.onlinePlayers, status: data.status || "WAITING" });
        } else if (data.type === "CHAT") {
            this.displayChatMessage(data.sender, data.role, data.text);
        } else if (data.type === "ERROR") {
            this.showToast(data.message, true);
        }
    }

    handleConnectionStatus(status) {
        const lobbyNetwork = document.getElementById("lobby-network-status");
        if (lobbyNetwork) {
            lobbyNetwork.textContent = status === "CONNECTED"
                ? "Connected · room updates are live"
                : status === "CONNECTING"
                    ? "Reconnecting to room…"
                    : "Connection interrupted · retrying automatically";
        }
        const dot = document.getElementById("net-status-dot");
        const label = document.getElementById("net-status-label");
        if (!dot || !label) return;

        if (status === "CONNECTED") {
            dot.className = "status-dot online";
            label.textContent = "ONLINE";
        } else if (status === "CONNECTING") {
            dot.className = "status-dot connecting";
            label.textContent = "CONNECTING";
        } else {
            dot.className = "status-dot offline";
            label.textContent = "OFFLINE";
        }
    }

    updatePlayersHUD(players) {
        for (let p = 1; p <= 4; p++) {
            const card = document.getElementById(`player-card-${p}`);
            if (!card) continue;
            const pData = players[p] || players[String(p)];
            const nameEl = card.querySelector(".player-name");
            const connDot = card.querySelector(".player-conn-dot");

            if (pData) {
                if (nameEl) nameEl.textContent = pData.name;
                if (connDot) connDot.className = `player-conn-dot ${pData.connected ? 'online' : 'offline'}`;
            } else {
                if (nameEl) nameEl.textContent = `Player ${p} (Open)`;
                if (connDot) connDot.className = "player-conn-dot offline";
            }
        }
    }

    handleUndo() {
        if (this.isOnlineMode) {
            this.showToast("Undo is disabled in Online Arena.", true);
            return;
        }
        const res = this.engine.undoMove();
        if (res.success) {
            window.soundSystem.playClick();
            this.ui.render();
            this.showToast("Move undone.");
        } else {
            this.showToast(res.message, true);
        }
    }

    handleRestart() {
        if (this.isOnlineMode) {
            fetch(`${window.CONFIG.getServerUrl()}/rooms/${encodeURIComponent(this.roomCode)}/reset`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ player_id: this.playerId }),
            }).then(async (response) => {
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || "Could not reset the room.");
            }).catch(error => this.showToast(error.message, true));
        } else {
            if (this.gameMode === "ai") this.startAIGame(this.aiDifficulty);
            else if (this.gameMode === "team") this.startTeamGame();
            else this.startLocalGame();
        }
    }

    handleResign() {
        if (confirm("Concede and resign this match?")) {
            if (this.isOnlineMode) {
                this.wsClient.send({ type: "RESIGN" });
            } else {
                this.engine.resignPlayer(this.engine.currentTurn);
                this.ui.render();
                this.showToast(`Player ${this.engine.currentTurn} resigned.`);
            }
        }
    }

    sendChatMessage(text) {
        if (!this.isOnlineMode) {
            this.displayChatMessage("Commander", this.engine.currentTurn, text);
            return;
        }
        this.wsClient.send({ type: "CHAT", text: text });
    }

    displayChatMessage(sender, role, text) {
        const info = window.PLAYER_INFO[role] || { color: "#fff" };
        const toast = document.createElement("div");
        toast.className = "chat-bubble-toast";
        toast.style.borderColor = info.color;
        toast.innerHTML = `<strong style="color:${info.color}">${sender}:</strong> ${text}`;

        const container = document.getElementById("toast-container");
        if (container) {
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 4000);
        }
    }

    showPassDevicePrompt(nextPlayer) {
        const modal = document.getElementById("pass-device-modal");
        const nameEl = document.getElementById("pass-next-player-name");
        const info = window.PLAYER_INFO[nextPlayer];

        if (nameEl && info) {
            nameEl.textContent = info.name;
            nameEl.style.color = info.color;
        }
        modal?.classList.remove("hidden");
    }

    /* ==================== DASHBOARD DATA & HISTORY ==================== */

    async initDashboardData() {
        try {
            const serverUrl = window.CONFIG.getServerUrl();
            const res = await fetch(`${serverUrl}/api/history`, { signal: AbortSignal.timeout(4000) });
            if (res.ok) {
                const history = await res.json();
                this.renderRecentMatches(history);
            } else {
                this.renderRecentMatches([]);
            }
        } catch (e) {
            // Non-deceptive: show authentic empty state if offline or no recorded matches yet
            this.renderRecentMatches([]);
        }
        window.FOURXProfile?.refresh();
    }

    renderRecentMatches(history) {
        const container = document.getElementById("dash-recent-matches");
        if (!container) return;

        if (!history || !Array.isArray(history) || history.length === 0) {
            container.innerHTML = `
                <div class="empty-history">
                    <span class="empty-history-icon">♞</span>
                    <p>No tournament records yet. Launch a 4-player battle to record match statistics.</p>
                </div>
            `;
            return;
        }

        container.innerHTML = history.slice(0, 5).map(m => `
            <div class="match-item">
                <div class="match-col">
                    <strong>Room #${m.room_code || 'LOCAL'}</strong>
                    <small>${m.total_moves} Moves · ${new Date(m.completed_at || Date.now()).toLocaleDateString()}</small>
                </div>
                <div class="match-result victory">${m.winner_name || 'Completed'}</div>
            </div>
        `).join("");
    }

    initPuzzlesList() {
        const container = document.getElementById("puzzles-container");
        if (!container || !window.PUZZLES_DATA) return;

        container.innerHTML = window.PUZZLES_DATA.map(p => `
            <div class="puzzle-item-card" data-id="${p.id}">
                <div class="puzzle-meta-left">
                    <strong>${p.title}</strong>
                    <p>${p.description}</p>
                    <small style="color:var(--color-p2); font-weight:700;">${p.difficulty} · ${p.rating} Elo</small>
                </div>
                <button class="mini-action-btn primary">Solve</button>
            </div>
        `).join("");

        container.querySelectorAll(".puzzle-item-card").forEach(card => {
            card.addEventListener("click", () => {
                const p = window.PUZZLES_DATA.find(x => x.id === card.dataset.id);
                if (p) this.startPuzzle(p);
            });
        });
    }

    initLeaderboardData() {
        const container = document.getElementById("leaderboard-body");
        if (!container) return;
        this.leaderboardFilters = {
            gameMode: "four_player",
            period: "all_time",
            category: "rating",
            offset: 0,
            limit: 25,
        };
        document.querySelectorAll("[data-lb-mode]").forEach(button => {
            button.addEventListener("click", () => {
                document.querySelectorAll("[data-lb-mode]").forEach(tab => tab.classList.toggle("active", tab === button));
                this.leaderboardFilters.gameMode = button.dataset.lbMode;
                this.leaderboardFilters.offset = 0;
                this.loadLeaderboard();
            });
        });
        document.querySelectorAll("[data-lb-period]").forEach(button => {
            button.addEventListener("click", () => {
                document.querySelectorAll("[data-lb-period]").forEach(tab => tab.classList.toggle("active", tab === button));
                this.leaderboardFilters.period = button.dataset.lbPeriod;
                this.leaderboardFilters.offset = 0;
                const category = document.getElementById("leaderboard-category");
                if (category) category.disabled = this.leaderboardFilters.period !== "all_time";
                this.loadLeaderboard();
            });
        });
        document.getElementById("leaderboard-category")?.addEventListener("change", (event) => {
            this.leaderboardFilters.category = event.target.value;
            this.leaderboardFilters.offset = 0;
            this.loadLeaderboard();
        });
        document.getElementById("leaderboard-search")?.addEventListener("input", () => {
            clearTimeout(this.leaderboardSearchTimeout);
            this.leaderboardSearchTimeout = setTimeout(() => {
                this.leaderboardFilters.offset = 0;
                this.loadLeaderboard();
            }, 250);
        });
        document.getElementById("leaderboard-prev")?.addEventListener("click", () => {
            this.leaderboardFilters.offset = Math.max(0, this.leaderboardFilters.offset - this.leaderboardFilters.limit);
            this.loadLeaderboard();
        });
        document.getElementById("leaderboard-next")?.addEventListener("click", () => {
            this.leaderboardFilters.offset += this.leaderboardFilters.limit;
            this.loadLeaderboard();
        });
        document.getElementById("leaderboard-profile-close")?.addEventListener("click", () => {
            document.getElementById("leaderboard-public-profile")?.classList.add("hidden");
        });
        this.loadLeaderboard();

    }

    async loadLeaderboard() {
        const container = document.getElementById("leaderboard-body");
        if (!container) return;
        const filters = this.leaderboardFilters;
        container.replaceChildren();
        try {
            const params = new URLSearchParams({
                game_mode: filters.gameMode,
                category: filters.category,
                period: filters.period,
                offset: String(filters.offset),
                limit: String(filters.limit),
            });
            const search = document.getElementById("leaderboard-search")?.value.trim();
            if (search) params.set("search", search);
            await window.FOURXProfile?.ready;
            const response = await fetch(
                `${window.CONFIG.getServerUrl()}/api/leaderboard?${params}`,
                { headers: window.FOURXProfile?.authHeaders() || {} }
            );
            const leaders = await response.json();
            if (!response.ok) throw new Error(leaders.detail || "Leaderboard unavailable");
            this.renderLeaderboardPodium(leaders.podium || []);
            this.renderLeaderboardCurrent(leaders.current_player);
            if (!leaders.entries?.length) {
                const empty = document.createElement("p");
                empty.className = "profile-empty";
                empty.textContent = "No players match this ranking yet. Complete online matches to appear here.";
                container.append(empty);
            } else {
                leaders.entries.forEach(leader => container.append(this.createLeaderboardRow(leader)));
            }
            const start = leaders.total ? filters.offset + 1 : 0;
            const end = Math.min(filters.offset + leaders.entries.length, leaders.total);
            const status = document.getElementById("leaderboard-page-status");
            if (status) status.textContent = `${start}-${end} of ${leaders.total} players`;
            const previous = document.getElementById("leaderboard-prev");
            const next = document.getElementById("leaderboard-next");
            if (previous) previous.disabled = filters.offset === 0;
            if (next) next.disabled = filters.offset + leaders.entries.length >= leaders.total;
        } catch (error) {
            const notice = document.createElement("p");
            notice.className = "profile-empty error";
            notice.textContent = `Leaderboard unavailable: ${error.message}`;
            container.append(notice);
        }
    }

    createLeaderboardRow(leader) {
        const row = document.createElement("div");
        row.className = "lb-row";
        const rank = document.createElement("span");
        rank.className = `lb-rank ${leader.rank <= 3 ? ["gold", "silver", "bronze"][leader.rank - 1] : ""}`;
        rank.textContent = `#${leader.rank}`;
        const player = document.createElement("div");
        player.className = "lb-player";
        const avatar = document.createElement("span");
        avatar.className = "lb-avatar";
        avatar.textContent = window.FOURX_AVATAR_ICONS[leader.avatar] || "♘";
        const view = document.createElement("button");
        view.type = "button";
        view.className = "lb-profile-link";
        view.textContent = leader.username;
        view.addEventListener("click", () => this.loadPublicProfile(leader.username));
        player.append(avatar, view);
        const score = document.createElement("span");
        score.className = "lb-rating";
        score.textContent = this.leaderboardFilters.category === "rating"
            && this.leaderboardFilters.period === "all_time"
            ? String(leader.rating)
            : String(leader.score);
        const games = document.createElement("span");
        games.textContent = String(leader.games);
        const win = document.createElement("span");
        win.className = "lb-win";
        win.textContent = `${leader.win_percentage}%`;
        const change = document.createElement("span");
        change.className = leader.rating_change > 0 ? "lb-change positive" : leader.rating_change < 0 ? "lb-change negative" : "lb-change";
        change.textContent = `${leader.rating_change > 0 ? "+" : ""}${leader.rating_change}`;
        row.append(rank, player, score, games, win, change);
        return row;
    }

    renderLeaderboardPodium(players) {
        const podium = document.getElementById("leaderboard-podium");
        if (!podium) return;
        podium.replaceChildren();
        players.forEach(player => {
            const card = document.createElement("button");
            card.type = "button";
            card.className = `lb-podium-card place-${player.rank}`;
            card.addEventListener("click", () => this.loadPublicProfile(player.username));
            const rank = document.createElement("span");
            rank.className = "lb-podium-rank";
            rank.textContent = `#${player.rank}`;
            const name = document.createElement("strong");
            name.textContent = player.username;
            const score = document.createElement("span");
            score.textContent = this.leaderboardFilters.category === "rating"
                && this.leaderboardFilters.period === "all_time"
                ? `${player.rating} rating`
                : `${player.score} score`;
            card.append(rank, name, score);
            podium.append(card);
        });
    }

    renderLeaderboardCurrent(current) {
        const panel = document.getElementById("leaderboard-current");
        if (!panel) return;
        panel.replaceChildren();
        panel.classList.toggle("hidden", !current);
        if (!current) return;
        const title = document.createElement("strong");
        title.textContent = `Your global position: #${current.rank}`;
        const neighbors = document.createElement("span");
        neighbors.textContent = current.neighbors.map(player => `#${player.rank} ${player.username}`).join(" · ");
        panel.append(title, neighbors);
    }

    async loadPublicProfile(username) {
        const panel = document.getElementById("leaderboard-public-profile");
        const content = document.getElementById("leaderboard-profile-content");
        if (!panel || !content) return;
        content.textContent = "Loading player profile…";
        panel.classList.remove("hidden");
        try {
            const response = await fetch(
                `${window.CONFIG.getServerUrl()}/api/players/${encodeURIComponent(username)}`
            );
            const profile = await response.json();
            if (!response.ok) throw new Error(profile.detail || "Public profile unavailable");
            content.replaceChildren();
            const heading = document.createElement("h3");
            heading.textContent = profile.username;
            const details = document.createElement("p");
            details.textContent = `Level ${profile.level} · ${profile.xp} XP · ${profile.games} games · ${profile.win_percentage}% wins`;
            const ratings = document.createElement("p");
            ratings.textContent = `Classic ${profile.ratings.classic} · Four-Player ${profile.ratings.four_player}`;
            content.append(heading, details, ratings);
        } catch (error) {
            content.textContent = `Profile unavailable: ${error.message}`;
        }
    }

    async testBackendConnection() {
        const statusEl = document.getElementById("backend-test-status");
        if (statusEl) statusEl.textContent = "Connecting to server...";

        try {
            const urlInput = document.getElementById("backend-url-input");
            const testUrl = (urlInput ? urlInput.value : window.CONFIG.getServerUrl()).trim().replace(/\/+$/, "");
            const res = await fetch(`${testUrl}/api/health`, { signal: AbortSignal.timeout(5000) });
            if (res.ok) {
                const data = await res.json();
                if (statusEl) {
                    statusEl.textContent = `✓ Server Online! (${data.service})`;
                    statusEl.style.color = "var(--color-success)";
                }
            } else {
                throw new Error(`HTTP ${res.status}`);
            }
        } catch (e) {
            if (statusEl) {
                statusEl.textContent = `✗ Connection Failed: ${e.message}`;
                statusEl.style.color = "var(--color-danger)";
            }
        }
    }

    showModal(modalId) {
        this.hideAllModals();
        document.getElementById(modalId)?.classList.remove("hidden");
        window.soundSystem.playClick();
    }

    hideAllModals() {
        document.querySelectorAll(".game-modal").forEach(m => m.classList.add("hidden"));
    }

    showToast(msg, isError = false) {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `neon-toast ${isError ? 'error-toast' : 'info-toast'}`;
        toast.textContent = msg;

        container.appendChild(toast);
        window.soundSystem.playNotification();
        setTimeout(() => toast.remove(), 3500);
    }

    updateSoundIcon(enabled) {
        const btn = document.getElementById("btn-sound-toggle");
        if (btn) {
            btn.innerHTML = enabled ? "🔊" : "🔇";
            btn.title = enabled ? "Mute Sound FX" : "Unmute Sound FX";
        }
    }
}

// Bootstrap on DOM Ready
window.addEventListener("DOMContentLoaded", () => {
    window.app = new QuadChessApp();
});
