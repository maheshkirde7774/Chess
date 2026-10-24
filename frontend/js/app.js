/**
 * Neon Four Chess - Main Application Controller
 * Manages game lifecycle, Local and Online multiplayer modes, modals, and network syncing.
 */

class NeonChessApp {
    constructor() {
        this.engine = new window.ClientChessEngine();
        this.isOnlineMode = false;
        this.roomCode = null;
        this.playerId = null;
        this.myRole = null; // 1: Cyan, 2: Magenta, 3: Lime, 4: Gold (for Online mode)
        this.onlinePlayers = {};

        this.wsClient = new window.WebSocketClient(
            (msg) => this.handleServerMessage(msg),
            (status) => this.handleConnectionStatus(status)
        );

        this.ui = new window.ChessUI(this.engine, (move, isCapture) => this.onPlayerMove(move, isCapture));

        this.initEventListeners();
        this.initSettingsValues();
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

    initEventListeners() {
        // Navigation Buttons
        document.getElementById("btn-nav-menu")?.addEventListener("click", () => this.showModal("menu-modal"));
        document.getElementById("btn-nav-rules")?.addEventListener("click", () => this.showModal("rules-modal"));
        document.getElementById("btn-nav-settings")?.addEventListener("click", () => this.showModal("settings-modal"));
        document.getElementById("btn-sound-toggle")?.addEventListener("click", () => {
            const isMuted = window.soundSystem.toggleMute();
            this.updateSoundIcon(!isMuted);
        });

        // Game Controls
        document.getElementById("btn-undo")?.addEventListener("click", () => this.handleUndo());
        document.getElementById("btn-restart")?.addEventListener("click", () => this.handleRestart());
        document.getElementById("btn-resign")?.addEventListener("click", () => this.handleResign());
        document.getElementById("btn-rotate")?.addEventListener("click", () => this.ui.manualRotate());

        // Menu Modal Actions
        document.getElementById("btn-mode-local")?.addEventListener("click", () => {
            this.startLocalGame();
            this.hideAllModals();
        });
        document.getElementById("btn-mode-create")?.addEventListener("click", () => {
            this.hideAllModals();
            this.showModal("create-room-modal");
        });
        document.getElementById("btn-mode-join")?.addEventListener("click", () => {
            this.hideAllModals();
            this.showModal("join-room-modal");
        });

        // Room Creation / Joining
        document.getElementById("form-create-room")?.addEventListener("submit", (e) => {
            e.preventDefault();
            const nameInput = document.getElementById("create-player-name");
            const name = nameInput ? nameInput.value.trim() : "Player 1";
            this.createOnlineRoom(name);
        });

        document.getElementById("form-join-room")?.addEventListener("submit", (e) => {
            e.preventDefault();
            const codeInput = document.getElementById("join-room-code");
            const nameInput = document.getElementById("join-player-name");
            const code = codeInput ? codeInput.value.trim().toUpperCase() : "";
            const name = nameInput ? nameInput.value.trim() : "Guest";
            if (code) {
                this.joinOnlineRoom(code, name);
            }
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

            this.showToast("Settings saved!");
            this.hideAllModals();
        });

        document.getElementById("btn-test-backend")?.addEventListener("click", () => this.testBackendConnection());

        // Copy Room Code
        document.getElementById("btn-copy-code")?.addEventListener("click", () => {
            if (this.roomCode) {
                navigator.clipboard.writeText(this.roomCode).then(() => {
                    this.showToast(`Room Code ${this.roomCode} copied to clipboard!`);
                }).catch(() => {
                    this.showToast(`Code: ${this.roomCode}`);
                });
            }
        });

        // Pass Device Screen Unlock
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
            this.showModal("menu-modal");
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
    }

    startLocalGame() {
        this.isOnlineMode = false;
        this.roomCode = null;
        this.playerId = null;
        this.myRole = null;
        this.wsClient.disconnect();

        document.getElementById("room-code-tag")?.classList.add("hidden");
        document.getElementById("network-indicator")?.classList.add("hidden");
        document.getElementById("btn-undo")?.classList.remove("hidden"); // Undo allowed in local mode

        this.engine = new window.ClientChessEngine();
        this.ui.engine = this.engine;
        this.ui.render();
        this.showToast("Local 4-Player Battle Initialized!");
    }

    async createOnlineRoom(playerName) {
        try {
            this.showToast("Contacting Neon server...");
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

            this.hideAllModals();
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);
            this.showToast(`Room ${this.roomCode} created! Share code with friends.`);
        } catch (e) {
            console.error("Room creation error:", e);
            this.showToast(`Error: ${e.message}`, true);
        }
    }

    async joinOnlineRoom(roomCode, playerName) {
        try {
            this.showToast(`Joining room ${roomCode}...`);
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

            this.hideAllModals();
            this.setupOnlineUI();
            this.wsClient.connect(this.roomCode, this.playerId);
            this.showToast(`Joined as ${window.PLAYER_INFO[this.myRole].name}!`);
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
        document.getElementById("btn-undo")?.classList.add("hidden"); // Disable undo in online mode
    }

    onPlayerMove(move, isCapture) {
        if (!this.isOnlineMode) {
            // Local Mode: execute move directly
            const prevTurn = this.engine.currentTurn;
            const res = this.engine.makeMove(move);
            if (res.success) {
                if (isCapture) window.soundSystem.playCapture();
                else window.soundSystem.playMove();

                if (this.engine.isInCheck(this.engine.currentTurn)) {
                    window.soundSystem.playCheck();
                }

                this.ui.render();

                // Optional Pass-Device prompt between turns in local mode
                if (window.CONFIG.isPassPromptEnabled() && !this.engine.isGameOver) {
                    this.showPassDevicePrompt(this.engine.currentTurn);
                }
            } else {
                this.showToast(res.message, true);
            }
        } else {
            // Online Mode: Send move to server over WebSocket
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

    handleServerMessage(data) {
        console.log("WebSocket event:", data.type, data);

        if (data.type === "SYNC_STATE") {
            if (data.your_role) this.myRole = data.your_role;
            if (data.players) this.updatePlayersHUD(data.players);
            if (data.game_state) {
                this.ui.render(data.game_state);
            }
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
            if (data.name) {
                this.showToast(`${data.name} connected!`);
            }
        } else if (data.type === "PLAYER_RESIGNED") {
            this.showToast(`Player ${data.player} has resigned.`);
            if (data.game_state) this.ui.render(data.game_state);
        } else if (data.type === "GAME_RESET") {
            this.showToast("Game has been reset by the room!");
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
            label.textContent = "DISCONNECTED";
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
                if (connDot) {
                    connDot.className = `player-conn-dot ${pData.connected ? 'online' : 'offline'}`;
                }
            } else {
                if (nameEl) nameEl.textContent = `Player ${p} (Open)`;
                if (connDot) connDot.className = "player-conn-dot offline";
            }
        }
    }

    handleUndo() {
        if (this.isOnlineMode) {
            this.showToast("Undo is only available in Local Mode.", true);
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
            this.startLocalGame();
        }
    }

    handleResign() {
        if (confirm("Are you sure you want to resign?")) {
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

        if (nameEl) {
            nameEl.textContent = info.name;
            nameEl.style.color = info.color;
        }
        modal?.classList.remove("hidden");
    }

    async testBackendConnection() {
        const statusEl = document.getElementById("backend-test-status");
        if (statusEl) statusEl.textContent = "Testing connection...";

        try {
            const urlInput = document.getElementById("backend-url-input");
            const testUrl = (urlInput ? urlInput.value : window.CONFIG.getServerUrl()).trim().replace(/\/+$/, "");
            const res = await fetch(`${testUrl}/api/health`, { signal: AbortSignal.timeout(5000) });
            if (res.ok) {
                const data = await res.json();
                if (statusEl) {
                    statusEl.textContent = `✓ Server Online! (${data.service})`;
                    statusEl.style.color = "#39ff14";
                }
            } else {
                throw new Error(`HTTP ${res.status}`);
            }
        } catch (e) {
            if (statusEl) {
                statusEl.textContent = `✗ Connection Failed: ${e.message}`;
                statusEl.style.color = "#ff007f";
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

// Bootstrap Application on DOM Ready
window.addEventListener("DOMContentLoaded", () => {
    window.app = new NeonChessApp();
    window.app.startLocalGame();
});
