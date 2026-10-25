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

        this.wsClient = new window.WebSocketClient(
            (msg) => this.handleServerMessage(msg),
            (status) => this.handleConnectionStatus(status)
        );

        this.ui = new window.ChessUI(this.engine, (move, isCapture) => this.onPlayerMove(move, isCapture));

        this.currentView = "view-home";
        this.initEventListeners();
        this.initSettingsValues();
        this.initDashboardData();
        this.initPuzzlesList();
        this.initLeaderboardData();
    }

    /* ==================== VIEW NAVIGATION ==================== */

    switchView(viewId) {
        document.querySelectorAll(".app-view").forEach(v => v.classList.remove("active-view"));
        const targetView = document.getElementById(viewId);
        if (targetView) {
            targetView.classList.add("active-view");
            this.currentView = viewId;
        }

        // Update Bottom Nav active state
        document.querySelectorAll(".nav-tab-btn").forEach(btn => {
            btn.classList.toggle("active", btn.dataset.target === viewId);
        });

        // Header adaptations
        const backBtn = document.getElementById("btn-back-home");
        const turnBadge = document.getElementById("turn-badge");
        const roomCodeTag = document.getElementById("room-code-tag");

        if (viewId === "view-game") {
            backBtn?.classList.remove("hidden");
            turnBadge?.classList.remove("hidden");
            if (this.isOnlineMode) roomCodeTag?.classList.remove("hidden");
        } else {
            backBtn?.classList.add("hidden");
            turnBadge?.classList.add("hidden");
            roomCodeTag?.classList.add("hidden");
        }

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

        // Brand Logo click -> Home
        document.getElementById("nav-brand-logo")?.addEventListener("click", () => {
            this.switchView("view-home");
        });

        // Header Action Buttons
        document.getElementById("btn-membership-header")?.addEventListener("click", () => {
            this.switchView("view-membership");
        });
        document.getElementById("btn-nav-rules")?.addEventListener("click", () => this.showModal("rules-modal"));
        document.getElementById("btn-nav-settings")?.addEventListener("click", () => this.showModal("settings-modal"));
        document.getElementById("btn-sound-toggle")?.addEventListener("click", () => {
            const isMuted = window.soundSystem.toggleMute();
            this.updateSoundIcon(!isMuted);
        });

        // Quick Play Hero Banner
        document.getElementById("btn-quick-play")?.addEventListener("click", () => {
            this.startAIGame("club");
        });

        // Dashboard Mode Cards
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
            this.startPuzzle(window.PUZZLES_DATA[0]);
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
            this.startAIGame(this.aiDifficulty);
        });

        // Notation Drawer Toggle
        document.getElementById("btn-toggle-notation")?.addEventListener("click", () => {
            const drawer = document.getElementById("notation-drawer");
            drawer?.classList.toggle("hidden");
        });
        document.getElementById("btn-close-notation")?.addEventListener("click", () => {
            document.getElementById("notation-drawer")?.classList.add("hidden");
        });

        // Game Controls
        document.getElementById("btn-undo")?.addEventListener("click", () => this.handleUndo());
        document.getElementById("btn-restart")?.addEventListener("click", () => this.handleRestart());
        document.getElementById("btn-resign")?.addEventListener("click", () => this.handleResign());
        document.getElementById("btn-rotate")?.addEventListener("click", () => this.ui.manualRotate());

        // Legacy / Modal Mode Buttons
        document.getElementById("btn-mode-local")?.addEventListener("click", () => {
            this.hideAllModals();
            this.startLocalGame();
        });
        document.getElementById("btn-mode-create")?.addEventListener("click", () => {
            this.hideAllModals();
            this.showModal("create-room-modal");
        });
        document.getElementById("btn-mode-join")?.addEventListener("click", () => {
            this.hideAllModals();
            this.showModal("join-room-modal");
        });

        // Friends Screen Actions
        document.getElementById("btn-open-create-room")?.addEventListener("click", () => {
            this.showModal("create-room-modal");
        });
        document.getElementById("btn-open-join-room")?.addEventListener("click", () => {
            this.showModal("join-room-modal");
        });

        // Forms: Create / Join Room
        document.getElementById("form-create-room")?.addEventListener("submit", (e) => {
            e.preventDefault();
            const nameInput = document.getElementById("create-player-name");
            const name = nameInput ? nameInput.value.trim() : "Grandmaster";
            this.createOnlineRoom(name);
        });

        document.getElementById("form-join-room")?.addEventListener("submit", (e) => {
            e.preventDefault();
            const codeInput = document.getElementById("join-room-code");
            const nameInput = document.getElementById("join-player-name");
            const code = codeInput ? codeInput.value.trim().toUpperCase() : "";
            const name = nameInput ? nameInput.value.trim() : "Guest";
            if (code) this.joinOnlineRoom(code, name);
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
        document.querySelectorAll(".modal-close-btn").forEach(btn => {
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
                window.CONFIG.setAudioEnabled(soundToggle.checked);
                window.soundSystem.muted = !soundToggle.checked;
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

        // Theme Switcher
        document.querySelectorAll(".theme-card").forEach(card => {
            card.addEventListener("click", (e) => {
                document.querySelectorAll(".theme-card").forEach(c => c.classList.remove("active"));
                e.currentTarget.classList.add("active");
                const theme = e.currentTarget.dataset.theme;
                this.applyBoardTheme(theme);
            });
        });

        // VIP Upgrade Button
        document.getElementById("btn-activate-pass")?.addEventListener("click", () => {
            this.showToast("Grandmaster Pass Activated! All themes & perks unlocked.");
            window.soundSystem.playVictory();
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

    applyBoardTheme(theme) {
        const board = document.getElementById("chessboard");
        if (!board) return;

        if (theme === "wood") {
            board.style.setProperty("--board-dark", "#8b5a2b");
            board.style.setProperty("--board-light", "#d2b48c");
            board.style.setProperty("--board-rim", "#4a2f13");
        } else if (theme === "carbon") {
            board.style.setProperty("--board-dark", "#1e222b");
            board.style.setProperty("--board-light", "#383f4f");
            board.style.setProperty("--board-rim", "#12141a");
        } else if (theme === "marble") {
            board.style.setProperty("--board-dark", "#334155");
            board.style.setProperty("--board-light", "#f1f5f9");
            board.style.setProperty("--board-rim", "#1e293b");
        } else {
            // Default slate
            board.style.removeProperty("--board-dark");
            board.style.removeProperty("--board-light");
            board.style.removeProperty("--board-rim");
        }
        this.showToast(`Applied ${theme.toUpperCase()} Board Theme`);
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
        this.showToast("Pass & Play Match Initialized");
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
        this.showToast(`Tactical Challenge: ${puzzle.description}`);
    }

    /* ==================== ONLINE MULTIPLAYER ==================== */

    async createOnlineRoom(playerName) {
        try {
            this.showToast("Creating Tournament Arena...");
            const serverUrl = window.CONFIG.getServerUrl();
            const res = await fetch(`${serverUrl}/rooms`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ player_name: playerName })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Failed to create room");
            }

            const data = await res.json();
            this.roomCode = data.room_code;
            this.playerId = data.player_id;
            this.myRole = data.player_role;
            this.isOnlineMode = true;
            this.gameMode = "online";

            this.hideAllModals();
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);

            this.switchView("view-game");
            this.showToast(`Room ${this.roomCode} created! Share code with friends.`);
        } catch (e) {
            console.error("Room creation error:", e);
            this.showToast(`Error: ${e.message}`, true);
        }
    }

    async joinOnlineRoom(roomCode, playerName) {
        try {
            this.showToast(`Connecting to room ${roomCode}...`);
            const serverUrl = window.CONFIG.getServerUrl();
            const res = await fetch(`${serverUrl}/rooms/join`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ room_code: roomCode, player_name: playerName })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || "Failed to join room");
            }

            const data = await res.json();
            this.roomCode = data.room_code;
            this.playerId = data.player_id;
            this.myRole = data.player_role;
            this.isOnlineMode = true;
            this.gameMode = "online";

            this.hideAllModals();
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);

            this.switchView("view-game");
            this.showToast(`Joined as ${window.PLAYER_INFO[this.myRole]?.name || 'Player'}!`);
        } catch (e) {
            console.error("Room join error:", e);
            this.showToast(`Error: ${e.message}`, true);
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
            if (data.players) this.updatePlayersHUD(data.players);
            if (data.game_state) this.ui.render(data.game_state);
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
            if (data.players) this.updatePlayersHUD(data.players);
            if (data.name) this.showToast(`${data.name} entered the arena`);
        } else if (data.type === "PLAYER_RESIGNED") {
            this.showToast(`Player ${data.player} resigned.`);
            if (data.game_state) this.ui.render(data.game_state);
        } else if (data.type === "GAME_RESET") {
            this.showToast("Arena reset for new match!");
            if (data.game_state) this.ui.render(data.game_state);
        } else if (data.type === "CHAT") {
            this.displayChatMessage(data.sender, data.role, data.text);
        } else if (data.type === "ERROR") {
            this.showToast(data.message, true);
        }
    }

    handleConnectionStatus(status) {
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
            const serverUrl = window.CONFIG.getServerUrl();
            fetch(`${serverUrl}/rooms/${this.roomCode}/reset`, { method: "POST" })
                .catch(err => console.error(err));
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
            }
        } catch (e) {
            // Fallback mock history if backend offline
            this.renderRecentMatches([
                { room_code: "QUAD88", winner_name: "Cyan (South)", total_moves: 28, completed_at: new Date().toISOString() },
                { room_code: "TOURN3", winner_name: "Lime (North)", total_moves: 44, completed_at: new Date().toISOString() }
            ]);
        }
    }

    renderRecentMatches(history) {
        const container = document.getElementById("dash-recent-matches");
        if (!container) return;

        if (!history || history.length === 0) {
            container.innerHTML = `<div class="match-item"><span style="color:var(--color-text-muted)">No recent matches yet. Start a match!</span></div>`;
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

        const mockLeaders = [
            { rank: 1, name: "Magnus_Q", rating: 2480, win: "78%", rankClass: "gold" },
            { rank: 2, name: "Hikaru_Quad", rating: 2415, win: "74%", rankClass: "silver" },
            { rank: 3, name: "ChessValkyrie", rating: 2360, win: "71%", rankClass: "bronze" },
            { rank: 4, name: "IronCommander", rating: 2190, win: "68%", rankClass: "" },
            { rank: 5, name: "Grandmaster (You)", rating: 1540, win: "68%", rankClass: "" },
            { rank: 6, name: "TacticalBishop", rating: 1520, win: "64%", rankClass: "" }
        ];

        container.innerHTML = mockLeaders.map(l => `
            <div class="lb-row">
                <span class="lb-rank ${l.rankClass}">#${l.rank}</span>
                <div class="lb-player">
                    <div class="lb-avatar">${l.name[0]}</div>
                    <span>${l.name}</span>
                </div>
                <span class="lb-rating">${l.rating}</span>
                <span class="lb-win">${l.win}</span>
            </div>
        `).join("");

        // Also friends list
        const friendsContainer = document.getElementById("friends-list-container");
        if (friendsContainer) {
            friendsContainer.innerHTML = `
                <div class="match-item">
                    <div class="lb-player">
                        <div class="lb-avatar">H</div>
                        <div>
                            <strong>Hikaru_Quad</strong>
                            <small style="color:var(--color-success)">● Online</small>
                        </div>
                    </div>
                    <button class="mini-action-btn primary" onclick="window.app.showModal('create-room-modal')">Challenge</button>
                </div>
                <div class="match-item">
                    <div class="lb-player">
                        <div class="lb-avatar">C</div>
                        <div>
                            <strong>ChessValkyrie</strong>
                            <small style="color:var(--color-success)">● In Game</small>
                        </div>
                    </div>
                    <button class="mini-action-btn">Spectate</button>
                </div>
            `;
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
