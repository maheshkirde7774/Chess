class SpectatorController {
    constructor(app) {
        this.app = app;
        this.socket = null;
        this.reconnectTimeout = null;
        this.lobbyInterval = null;
        this.clockInterval = setInterval(() => this.updateTimers(), 1000);
        this.explicitlyClosed = true;
        this.isReplay = false;
        this.isCompleted = false;
        this.rotated = false;
        this.match = null;
        this.gameState = null;
        this.players = {};
        this.moveHistory = [];
        this.spectatorCount = 0;
        this.serverClockOffset = 0;
        this.serverStateAt = 0;
        this.durationAtSync = 0;
        this.durationSyncAt = 0;
        this.replayPositions = [];
        this.replayMoves = [];
        this.replayIndex = 0;
        this.replayTimer = null;
        this.reconnectAttempts = 0;
        this.accessToken = null;
        this.bindEvents();
    }

    bindEvents() {
        document.getElementById("live-game-mode-filter")?.addEventListener("change", () => this.renderLiveGames());
        document.getElementById("live-game-sort")?.addEventListener("change", () => this.renderLiveGames());
        document.getElementById("live-game-refresh")?.addEventListener("click", () => this.loadLobby());
        document.getElementById("private-spectator-form")?.addEventListener("submit", event => {
            event.preventDefault();
            const roomCode = document.getElementById("private-spectator-code")?.value.trim().toUpperCase();
            const accessToken = document.getElementById("private-spectator-key")?.value.trim();
            const gameMode = document.getElementById("private-spectator-mode")?.value;
            if (roomCode && accessToken) this.watch({ room_code: roomCode, game_mode: gameMode }, accessToken);
        });
        document.getElementById("spectator-leave")?.addEventListener("click", () => this.leave());
        document.getElementById("spectator-orientation")?.addEventListener("click", () => {
            this.rotated = !this.rotated;
            this.renderBoard();
        });
        document.getElementById("spectator-fullscreen")?.addEventListener("click", () => this.toggleFullscreen());
        document.getElementById("spectator-replay-previous")?.addEventListener("click", () => this.showReplayPosition(this.replayIndex - 1));
        document.getElementById("spectator-replay-next")?.addEventListener("click", () => this.showReplayPosition(this.replayIndex + 1));
        document.getElementById("spectator-replay-play")?.addEventListener("click", () => this.toggleReplay());
        document.addEventListener("fullscreenchange", () => {
            const button = document.getElementById("spectator-fullscreen");
            if (button) button.textContent = document.fullscreenElement ? "Exit fullscreen" : "Fullscreen board";
        });
    }

    onLobbyEntered() {
        this.loadLobby();
        clearInterval(this.lobbyInterval);
        this.lobbyInterval = setInterval(() => {
            if (this.app.currentView === "view-live-games") this.loadLobby();
        }, 15000);
    }

    onLobbyExited() {
        clearInterval(this.lobbyInterval);
        this.lobbyInterval = null;
    }

    onSpectatorExited() {
        this.explicitlyClosed = true;
        this.stopSocket();
        this.stopReplay();
        this.accessToken = null;
    }

    async loadLobby() {
        const gamesList = document.getElementById("live-games-list");
        const replaysList = document.getElementById("live-replays-list");
        if (!gamesList || !replaysList) return;
        try {
            const [gamesResponse, replaysResponse] = await Promise.all([
                fetch(`${window.CONFIG.getServerUrl()}/spectator/live-games`),
                fetch(`${window.CONFIG.getServerUrl()}/spectator/replays`),
            ]);
            const [games, replays] = await Promise.all([
                gamesResponse.json(),
                replaysResponse.json(),
            ]);
            if (!gamesResponse.ok) throw new Error(games.detail || "Could not load live games.");
            if (!replaysResponse.ok) throw new Error(replays.detail || "Could not load completed matches.");
            this.liveGames = Array.isArray(games) ? games : [];
            this.completedMatches = Array.isArray(replays) ? replays : [];
            this.renderLiveGames();
            this.renderReplays();
        } catch (error) {
            gamesList.textContent = `Live games unavailable: ${error.message}`;
            replaysList.textContent = `Replays unavailable: ${error.message}`;
        }
    }

    renderLiveGames() {
        const container = document.getElementById("live-games-list");
        if (!container) return;
        const mode = document.getElementById("live-game-mode-filter")?.value || "all";
        const sort = document.getElementById("live-game-sort")?.value || "popular";
        const games = (this.liveGames || []).filter(game =>
            mode === "all" || game.game_mode === mode
        );
        games.sort(sort === "popular"
            ? (left, right) => right.spectator_count - left.spectator_count
            : (left, right) => Date.parse(right.started_at || 0) - Date.parse(left.started_at || 0));
        container.replaceChildren();
        if (!games.length) {
            container.textContent = "No public matches are live right now.";
            return;
        }
        games.forEach(game => container.append(this.createGameCard(game)));
    }

    renderReplays() {
        const container = document.getElementById("live-replays-list");
        if (!container) return;
        container.replaceChildren();
        const matches = this.completedMatches || [];
        if (!matches.length) {
            container.textContent = "No completed public online matches are available to replay.";
            return;
        }
        matches.forEach(match => {
            const card = document.createElement("article");
            card.className = "live-game-card replay-card";
            const details = document.createElement("div");
            const title = document.createElement("strong");
            title.textContent = `${match.game_mode === "classic" ? "Classic 1v1" : "Four-Player Chess"} · ${match.players.join(" vs ")}`;
            const summary = document.createElement("p");
            summary.textContent = `${match.result} · ${this.formatDuration(match.duration_seconds)} · Room ${match.room_code}`;
            details.append(title, summary);
            const button = document.createElement("button");
            button.className = "neon-btn secondary-btn";
            button.type = "button";
            button.textContent = "Replay Match";
            button.addEventListener("click", () => this.loadReplay(match));
            card.append(details, button);
            container.append(card);
        });
    }

    createGameCard(game) {
        const card = document.createElement("article");
        card.className = "live-game-card";
        const details = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = game.game_mode === "classic" ? "Classic 1v1" : "Four-Player Chess";
        const names = Object.values(game.players || {}).map(player => player.name).filter(Boolean);
        const players = document.createElement("p");
        players.textContent = names.length ? names.join(" · ") : "Player names unavailable";
        const meta = document.createElement("small");
        meta.textContent = `${game.status} · ${game.spectator_count} watching · ${this.formatDuration(game.duration_seconds)} · Room ${game.room_code}`;
        details.append(title, players, meta);
        const watch = document.createElement("button");
        watch.className = "neon-btn primary-btn";
        watch.type = "button";
        watch.textContent = "Watch Match";
        watch.addEventListener("click", () => this.watch(game));
        card.append(details, watch);
        return card;
    }

    async watch(game, accessToken = null) {
        this.explicitlyClosed = true;
        this.stopSocket();
        this.stopReplay();
        this.isReplay = false;
        this.isCompleted = false;
        this.explicitlyClosed = false;
        this.match = game;
        this.accessToken = accessToken;
        this.startedAt = game.started_at ? Date.parse(game.started_at) : null;
        this.durationAtSync = game.duration_seconds || 0;
        this.durationSyncAt = Date.now();
        this.gameState = null;
        this.players = game.players || {};
        this.spectatorCount = game.spectator_count || 0;
        this.moveHistory = [];
        this.app.switchView("view-spectator");
        this.renderShell();
        this.connect();
    }

    connect() {
        if (!this.match || this.explicitlyClosed || this.isReplay) return;
        const code = encodeURIComponent(this.match.room_code);
        const path = this.match.game_mode === "classic"
            ? `/spectate/classic/${code}`
            : `/spectate/${code}`;
        const socket = new WebSocket(`${window.CONFIG.getWsUrl()}${path}`);
        this.socket = socket;
        socket.onopen = () => {
            if (this.socket !== socket) return;
            const message = { type: "SPECTATE" };
            if (this.accessToken) message.access_token = this.accessToken;
            socket.send(JSON.stringify(message));
        };
        socket.onmessage = event => {
            if (this.socket !== socket) return;
            try {
                this.handleMessage(JSON.parse(event.data));
            } catch (error) {
                console.error("Could not read spectator update:", error);
            }
        };
        socket.onerror = () => this.setConnectionLabel("Connection interrupted · reconnecting…");
        socket.onclose = event => {
            if (this.socket !== socket) return;
            this.socket = null;
            if (event.code === 1008) {
                this.explicitlyClosed = true;
                this.setConnectionLabel("Match unavailable or spectator key invalid.");
                return;
            }
            if (!this.explicitlyClosed && !this.isCompleted) {
                if (this.reconnectAttempts >= 8) {
                    this.explicitlyClosed = true;
                    this.setConnectionLabel("Could not reconnect. Leave and try again.");
                    return;
                }
                this.setConnectionLabel("Connection interrupted · reconnecting…");
                clearTimeout(this.reconnectTimeout);
                const delay = Math.min(1000 * (2 ** this.reconnectAttempts), 15000);
                this.reconnectAttempts += 1;
                this.reconnectTimeout = setTimeout(() => this.connect(), delay);
            }
        };
    }

    handleMessage(message) {
        if (message.type === "SYNC_STATE") {
            this.match = { ...this.match, ...message };
            this.reconnectAttempts = 0;
            this.gameState = message.game_state;
            this.players = message.players || this.players;
            this.moveHistory = message.move_history || this.gameState?.moves || [];
            this.spectatorCount = message.spectator_count || 0;
            this.setServerTime(message.server_time, message.started_at, 0);
            this.renderShell();
            this.renderMatch();
            return;
        }
        if (message.type === "SPECTATOR_COUNT") {
            this.spectatorCount = message.spectator_count || 0;
            this.renderShell();
            return;
        }
        if (message.type === "TIMER_SYNC" || message.type === "PONG") {
            this.setServerTime(message.server_time, null, message.duration_seconds || 0);
            if (message.clocks && this.gameState) {
                this.gameState.clocks = message.clocks;
                this.gameState.turn = message.turn || this.gameState.turn;
                this.serverStateAt = Date.now();
                this.renderMatch();
            }
            return;
        }
        if (message.type === "ERROR") {
            this.setConnectionLabel(message.message || "Spectator connection error");
            return;
        }
        if (message.players) this.players = message.players;
        if (message.game_state) {
            this.gameState = message.game_state;
            this.moveHistory = message.game_state.moves || this.moveHistory;
            if (message.server_time) this.serverClockOffset = message.server_time * 1000 - Date.now();
            this.serverStateAt = Date.now();
        }
        if (message.type === "MOVE_MADE" && this.match.game_mode === "four_player" && message.move) {
            this.moveHistory.push({ ...message.move, player: message.player });
        }
        if (message.spectator_count !== undefined) this.spectatorCount = message.spectator_count;
        if (message.status === "COMPLETED" || message.is_game_over
            || this.gameState?.status === "COMPLETED" || this.gameState?.is_game_over) {
            this.isCompleted = true;
            this.setLiveIndicator(false, "MATCH COMPLETE");
        }
        this.renderShell();
        this.renderMatch();
    }

    setServerTime(serverTime, startedAt, duration) {
        if (serverTime) this.serverClockOffset = serverTime * 1000 - Date.now();
        if (startedAt) {
            const parsed = Date.parse(startedAt);
            if (!Number.isNaN(parsed)) this.startedAt = parsed;
        }
        if (duration !== undefined) {
            this.durationAtSync = duration;
            this.durationSyncAt = Date.now();
        }
        this.serverStateAt = Date.now();
    }

    renderShell() {
        if (!this.match) return;
        const gameMode = this.match.game_mode || this.match.gameMode;
        document.getElementById("spectator-match-title").textContent =
            gameMode === "classic" ? "Classic 1v1" : "Four-Player Chess";
        document.getElementById("spectator-match-subtitle").textContent =
            `Room ${this.match.room_code || ""} · ${this.isReplay ? "Completed match replay" : "Read-only spectator mode"}`;
        document.getElementById("spectator-count").textContent =
            this.isReplay ? "Replay" : `${this.spectatorCount} watching`;
        document.getElementById("spectator-replay-controls")?.classList.toggle("hidden", !this.isReplay);
        document.getElementById("spectator-leave").textContent = this.isReplay
            ? "Back to Live Games"
            : "Leave Spectator Mode";
        const indicator = this.isReplay ? "REPLAY" : this.isCompleted ? "MATCH COMPLETE" : "LIVE";
        this.setLiveIndicator(!this.isReplay && !this.isCompleted, indicator);
    }

    renderMatch() {
        if (!this.gameState) return;
        this.renderBoard();
        this.renderPlayers();
        this.renderHistory();
        this.updateStatus();
        this.updateTimers();
        const result = document.getElementById("spectator-result");
        if (result) {
            const finalResult = this.isReplay ? this.match.result : this.gameState.result;
            result.textContent = finalResult ? `Final result: ${finalResult}` : "";
            result.classList.toggle("hidden", !finalResult && !this.isCompleted);
            if (this.isCompleted && !finalResult) result.textContent = "Match complete";
        }
    }

    renderBoard() {
        const board = document.getElementById("spectator-board");
        if (!board || !this.gameState) return;
        const gameMode = this.match.game_mode || this.match.gameMode;
        board.className = `spectator-board-grid ${gameMode === "classic" ? "classic" : "four-player"}`;
        if (gameMode === "classic") {
            const fen = typeof this.gameState === "string" ? this.gameState : this.gameState.fen;
            const rows = this.parseFen(fen);
            const cells = [];
            const ranks = this.rotated ? [...rows].reverse().map(row => [...row].reverse()) : rows;
            ranks.forEach((row, rank) => row.forEach((piece, file) => {
                const square = document.createElement("div");
                square.className = `spectator-square ${(rank + file) % 2 ? "dark" : "light"}`;
                square.setAttribute("role", "gridcell");
                square.setAttribute("aria-label", piece ? this.pieceName(piece) : "Empty square");
                if (piece) square.textContent = this.classicSymbol(piece);
                cells.push(square);
            }));
            board.replaceChildren(...cells);
            return;
        }
        const position = this.gameState;
        const source = position.board || [];
        const coordinates = [];
        for (let row = 0; row < 14; row++) {
            for (let column = 0; column < 14; column++) coordinates.push([row, column]);
        }
        if (this.rotated) coordinates.reverse();
        board.replaceChildren(...coordinates.map(([row, column], index) => {
            const piece = source[row]?.[column];
            const cell = document.createElement("div");
            cell.className = `spectator-four-square${piece === "VOID" ? " void" : ""}`;
            cell.setAttribute("role", "gridcell");
            if (piece && piece !== "VOID") {
                const content = document.createElement("span");
                content.textContent = this.fourPlayerSymbol(piece.type);
                content.style.color = this.playerColor(piece.player);
                cell.setAttribute("aria-label", `Player ${piece.player} ${piece.type}`);
                if (piece.is_dormant) content.classList.add("dormant");
                cell.append(content);
            } else {
                cell.setAttribute("aria-label", piece === "VOID" ? "Outside board" : "Empty square");
            }
            cell.classList.toggle("alt", index % 2 === 1);
            return cell;
        }));
    }

    renderPlayers() {
        const container = document.getElementById("spectator-players");
        if (!container) return;
        const entries = Object.entries(this.players || {});
        container.replaceChildren(...entries.map(([key, player]) => {
            const card = document.createElement("div");
            card.className = "spectator-player-card";
            const avatar = document.createElement("span");
            avatar.className = "spectator-avatar";
            avatar.textContent = this.avatarLabel(player);
            const info = document.createElement("div");
            const name = document.createElement("strong");
            name.textContent = player.name || key;
            const state = document.createElement("small");
            state.textContent = player.connected === false ? "Disconnected" : "Connected";
            info.append(name, state);
            card.append(avatar, info);
            if ((this.match.game_mode || this.match.gameMode) === "classic") {
                const clock = document.createElement("time");
                clock.className = "spectator-clock";
                clock.dataset.side = key;
                card.append(clock);
            }
            if (player.color) card.style.setProperty("--player-accent", player.color);
            else if (player.role) card.style.setProperty("--player-accent", this.playerColor(player.role));
            return card;
        }));
    }

    renderHistory() {
        const container = document.getElementById("spectator-move-history");
        if (!container) return;
        const gameMode = this.match.game_mode || this.match.gameMode;
        const moves = this.isReplay ? this.replayMoves : this.moveHistory;
        container.replaceChildren(...moves.map((move, index) => {
            const row = document.createElement("li");
            if (gameMode === "classic") {
                row.textContent = `${Math.floor(index / 2) + 1}. ${move.san || move.uci || "Move"}`;
            } else {
                const from = Array.isArray(move.from) ? move.from.join(",") : "";
                const to = Array.isArray(move.to) ? move.to.join(",") : "";
                row.textContent = `P${move.player || move.piece?.player || "?"}: ${from} → ${to}`;
            }
            if (this.isReplay && index + 1 === this.replayIndex) row.classList.add("active");
            return row;
        }));
        container.scrollTop = container.scrollHeight;
    }

    updateStatus() {
        const element = document.getElementById("spectator-match-status");
        if (!element || !this.gameState) return;
        const gameMode = this.match.game_mode || this.match.gameMode;
        let label;
        if (gameMode === "classic") {
            const turn = this.gameState.turn || "white";
            const player = this.players[turn]?.name || turn;
            label = `${this.isCompleted ? "Completed" : "Current turn"}: ${player}`;
            if (this.gameState.in_check) label += " · Check";
        } else {
            const turn = this.gameState.current_turn;
            const player = this.players[String(turn)]?.name || `Player ${turn}`;
            label = `${this.isCompleted ? "Completed" : "Current turn"}: ${player}`;
        }
        if (this.isReplay) label = `Replay position ${this.replayIndex} of ${this.replayMoves.length}`;
        element.textContent = label;
    }

    updateTimers() {
        if (!this.match) return;
        const elapsed = this.durationAtSync + Math.max(0, Date.now() - this.durationSyncAt) / 1000;
        document.getElementById("spectator-duration").textContent = this.formatDuration(
            this.startedAt ? Math.floor((Date.now() + this.serverClockOffset - this.startedAt) / 1000) : elapsed
        );
        if ((this.match.game_mode || this.match.gameMode) !== "classic" || !this.gameState?.clocks) return;
        const clocks = this.gameState.clocks;
        const turn = this.gameState.turn;
        for (const side of ["white", "black"]) {
            const seconds = clocks[side];
            const clock = document.querySelector(`.spectator-clock[data-side="${side}"]`);
            if (!clock) continue;
            if (seconds === null || seconds === undefined) {
                clock.textContent = "Clock ∞";
                continue;
            }
            const value = side === turn
                ? Math.max(0, seconds - (Date.now() + this.serverClockOffset - this.serverStateAt) / 1000)
                : seconds;
            clock.textContent = `Clock ${this.formatDuration(value)}`;
        }
    }

    setConnectionLabel(message) {
        const status = document.getElementById("spectator-match-status");
        if (status) status.textContent = message;
        this.setLiveIndicator(false, "RECONNECTING");
    }

    setLiveIndicator(active, label) {
        const indicator = document.getElementById("spectator-live-indicator");
        if (!indicator) return;
        indicator.classList.toggle("completed", !active);
        indicator.innerHTML = `<i></i>${label}`;
    }

    parseFen(fen) {
        if (!fen) return [];
        return fen.split(" ")[0].split("/").map(rank => {
            const squares = [];
            for (const cell of rank) {
                if (/\d/.test(cell)) {
                    for (let i = 0; i < Number(cell); i++) squares.push(null);
                } else squares.push(cell);
            }
            return squares;
        });
    }

    classicSymbol(piece) {
        const symbols = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
            k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
        return symbols[piece] || "";
    }

    fourPlayerSymbol(type) {
        return ({ K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙" })[type] || "";
    }

    playerColor(role) {
        return ({ 1: "#00f3ff", 2: "#ff007f", 3: "#a78bfa", 4: "#ffd700" })[role] || "#f4f4f5";
    }

    avatarLabel(player) {
        const icons = window.FOURX_AVATAR_ICONS || {
            king: "♔", queen: "♕", rook: "♖", bishop: "♗", knight: "♘", pawn: "♙",
        };
        if (icons[player.avatar]) return icons[player.avatar];
        return (player.name || "?").trim().charAt(0).toUpperCase() || "?";
    }

    pieceName(piece) {
        const names = { K: "White king", Q: "White queen", R: "White rook", B: "White bishop", N: "White knight", P: "White pawn",
            k: "Black king", q: "Black queen", r: "Black rook", b: "Black bishop", n: "Black knight", p: "Black pawn" };
        return names[piece] || "Empty square";
    }

    async toggleFullscreen() {
        const element = document.getElementById("spectator-board-wrap");
        try {
            if (document.fullscreenElement) await document.exitFullscreen();
            else await element?.requestFullscreen();
        } catch (error) {
            this.app.showToast(`Fullscreen unavailable: ${error.message}`, true);
        }
    }

    async loadReplay(match) {
        this.explicitlyClosed = true;
        this.stopSocket();
        this.stopReplay();
        try {
            const response = await fetch(
                `${window.CONFIG.getServerUrl()}/spectator/replays/${encodeURIComponent(match.match_id)}`
            );
            const replay = await response.json();
            if (!response.ok) throw new Error(replay.detail || "Replay unavailable.");
            this.match = replay;
            this.isReplay = true;
            this.isCompleted = true;
            this.replayPositions = replay.positions || [];
            this.replayMoves = replay.moves || [];
            this.replayIndex = 0;
            this.players = Object.fromEntries((replay.players || []).map((name, index) => [
                replay.game_mode === "classic" ? (index ? "black" : "white") : String(index + 1),
                { name },
            ]));
            this.gameState = replay.game_mode === "classic"
                ? { fen: this.replayPositions[0], turn: "white", moves: [] }
                : this.replayPositions[0];
            this.explicitlyClosed = true;
            this.app.switchView("view-spectator");
            this.renderShell();
            this.renderMatch();
        } catch (error) {
            this.app.showToast(error.message, true);
        }
    }

    showReplayPosition(position) {
        if (!this.isReplay || !this.replayPositions.length) return;
        this.replayIndex = Math.max(0, Math.min(this.replayPositions.length - 1, position));
        const state = this.replayPositions[this.replayIndex];
        if (this.match.game_mode === "classic") {
            const moves = this.replayMoves.slice(0, this.replayIndex);
            this.gameState = {
                fen: state,
                turn: this.parseFenTurn(state),
                moves,
                status: this.replayIndex === this.replayPositions.length - 1 ? "COMPLETED" : "PLAYING",
            };
        } else {
            this.gameState = state;
        }
        document.getElementById("spectator-replay-position").textContent =
            `Move ${this.replayIndex} of ${this.replayMoves.length}`;
        this.renderMatch();
    }

    parseFenTurn(fen) {
        return fen?.split(" ")[1] === "b" ? "black" : "white";
    }

    toggleReplay() {
        if (this.replayTimer) {
            this.stopReplay();
            return;
        }
        const interval = Number(document.getElementById("spectator-replay-speed")?.value) || 1000;
        document.getElementById("spectator-replay-play").textContent = "Pause";
        this.replayTimer = setInterval(() => {
            if (this.replayIndex >= this.replayPositions.length - 1) {
                this.stopReplay();
                return;
            }
            this.showReplayPosition(this.replayIndex + 1);
        }, interval);
    }

    stopReplay() {
        clearInterval(this.replayTimer);
        this.replayTimer = null;
        const button = document.getElementById("spectator-replay-play");
        if (button) button.textContent = "Play";
    }

    stopSocket() {
        clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = null;
        if (this.socket) {
            const socket = this.socket;
            this.socket = null;
            try { socket.close(); } catch (error) { console.warn("Could not close spectator socket:", error); }
        }
    }

    leave() {
        this.explicitlyClosed = true;
        this.stopSocket();
        this.stopReplay();
        this.match = null;
        this.gameState = null;
        this.isReplay = false;
        this.isCompleted = false;
        this.accessToken = null;
        this.app.switchView("view-live-games");
    }

    formatDuration(seconds) {
        const total = Math.max(0, Math.floor(Number(seconds) || 0));
        const hours = Math.floor(total / 3600);
        const minutes = Math.floor((total % 3600) / 60);
        const remainder = total % 60;
        return hours
            ? `${hours}:${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`
            : `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
    }
}

window.SpectatorController = SpectatorController;
