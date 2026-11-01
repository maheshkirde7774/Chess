class ClassicChessUI {
    constructor(app) {
        this.app = app;
        this.roomCode = null;
        this.playerId = null;
        this.mySide = null;
        this.mode = null;
        this.roomStatus = "WAITING";
        this.state = null;
        this.players = {};
        this.selectedSquare = null;
        this.socket = null;
        this.socketEnabled = false;
        this.reconnectTimeout = null;
        this.pingInterval = null;
        this.serverStateAt = 0;
        this.serverClockOffset = null;
        this.clockInterval = setInterval(() => this.renderClocks(), 250);
        this.bindEvents();
        this.restoreSession();
    }

    async copyRoomCode() {
        try {
            await navigator.clipboard.writeText(this.roomCode);
            this.app.showToast("Room code copied.");
        } catch (error) {
            this.app.showToast(`Share room code: ${this.roomCode}`);
        }
    }

    async shareRoom() {
        const invite = {
            title: "FOURX Classic Chess invitation",
            text: `Join my FOURX Classic Chess room. Room code: ${this.roomCode}`,
            url: window.location.href,
        };
        try {
            if (navigator.share) await navigator.share(invite);
            else await this.copyRoomCode();
        } catch (error) {
            if (error.name !== "AbortError") this.app.showToast(`Share room code: ${this.roomCode}`);
        }
    }

    async leaveRoom() {
        try {
            await this.request(
                `/classic/rooms/${encodeURIComponent(this.roomCode)}/leave`,
                {
                    method: "POST",
                    body: JSON.stringify({ player_id: this.playerId }),
                }
            );
            this.socketEnabled = false;
            clearInterval(this.pingInterval);
            clearTimeout(this.reconnectTimeout);
            this.socket?.close();
            sessionStorage.removeItem("classicChessSession");
            this.roomCode = null;
            this.playerId = null;
            this.state = null;
            this.app.switchView("view-home");
        } catch (error) {
            this.app.showToast(error.message, true);
        }
    }

    bindEvents() {
        document.getElementById("classic-start-local")?.addEventListener("click", () => {
            this.startRoom("local");
        });
        document.getElementById("classic-start-match")?.addEventListener("click", () => {
            this.send({ type: "START_GAME" });
        });
        document.getElementById("classic-ready")?.addEventListener("click", (event) => {
            const button = event.currentTarget;
            button.dataset.ready = button.dataset.ready !== "true" ? "true" : "false";
            this.send({ type: "READY", ready: button.dataset.ready === "true" });
        });
        document.getElementById("classic-leave-room")?.addEventListener("click", () => this.leaveRoom());
        document.getElementById("classic-copy-code")?.addEventListener("click", () => this.copyRoomCode());
        document.getElementById("classic-share-room")?.addEventListener("click", () => this.shareRoom());
        document.getElementById("classic-create-online")?.addEventListener("click", () => {
            this.startRoom("online");
        });
        document.getElementById("classic-join-online")?.addEventListener("click", () => {
            this.joinRoom();
        });
        document.getElementById("classic-back-home")?.addEventListener("click", () => {
            this.app.switchView("view-home");
        });
        document.getElementById("classic-result-home")?.addEventListener("click", () => {
            document.getElementById("classic-result")?.classList.add("hidden");
            this.app.switchView("view-home");
        });
        document.getElementById("classic-resign")?.addEventListener("click", () => {
            if (this.state?.status === "PLAYING" && confirm("Resign this classic match?")) {
                this.send({ type: "RESIGN" });
            }
        });
        document.getElementById("classic-offer-draw")?.addEventListener("click", () => {
            this.send({ type: "OFFER_DRAW" });
        });
        document.getElementById("classic-claim-draw")?.addEventListener("click", () => {
            this.send({ type: "CLAIM_DRAW" });
        });
        document.getElementById("classic-accept-draw")?.addEventListener("click", () => {
            this.send({ type: "ACCEPT_DRAW" });
        });
        document.getElementById("classic-decline-draw")?.addEventListener("click", () => {
            this.send({ type: "DECLINE_DRAW" });
        });
        document.getElementById("classic-board")?.addEventListener("click", (event) => {
            const square = event.target.closest("[data-square]");
            if (square) this.selectSquare(square.dataset.square);
        });
    }

    async request(path, options = {}) {
        const response = await fetch(`${window.CONFIG.getServerUrl()}${path}`, {
            ...options,
            headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Classic chess request failed");
        return data;
    }

    get timeControl() {
        return document.getElementById("classic-time-control")?.value || "10+0";
    }

    get playerName() {
        return document.getElementById("classic-player-name")?.value.trim() || "Player";
    }

    async startRoom(mode) {
        try {
            const data = await this.request("/classic/rooms", {
                method: "POST",
                body: JSON.stringify({
                    player_name: this.playerName,
                    time_control: this.timeControl,
                    mode,
                }),
            });
            this.enterRoom(data, mode);
        } catch (error) {
            this.app.showToast(error.message, true);
        }
    }

    async createOnlineRoom(playerName, timeControl, isPrivate = true) {
        try {
            const data = await this.request("/classic/rooms", {
                method: "POST",
                body: JSON.stringify({
                    player_name: playerName,
                    time_control: timeControl,
                    mode: "online",
                    is_private: isPrivate,
                }),
            });
            this.enterRoom(data, "online");
        } catch (error) {
            this.app.showToast(error.message, true);
        }
    }

    async joinRoom() {
        const roomCode = document.getElementById("classic-join-code")?.value.trim().toUpperCase();
        if (!roomCode) {
            this.app.showToast("Enter a classic room code.", true);
            return;
        }
        await this.joinRoomWithCode(roomCode, this.playerName);
    }

    async joinRoomWithCode(roomCode, playerName) {
        try {
            const data = await this.request("/classic/rooms/join", {
                method: "POST",
                body: JSON.stringify({ room_code: roomCode, player_name: playerName }),
            });
            this.enterRoom(data, "online");
        } catch (error) {
            this.app.showToast(error.message, true);
        }
    }

    enterRoom(data, mode) {
        this.roomCode = data.room_code;
        this.playerId = data.player_id;
        this.mySide = data.your_side;
        this.mode = mode;
        this.players = data.players || {};
        this.state = data.game_state;
        this.serverStateAt = Date.now();
        this.updateServerClock(data.server_time);
        sessionStorage.setItem("classicChessSession", JSON.stringify({
            roomCode: this.roomCode,
            playerId: this.playerId,
            mode: this.mode,
            mySide: this.mySide,
        }));
        this.app.hideAllModals();
        document.getElementById("classic-room-tag")?.classList.toggle("hidden", mode !== "online");
        document.getElementById("classic-room-code").textContent = this.roomCode;
        document.getElementById("classic-leave-room")?.classList.toggle("hidden", mode !== "online");
        document.getElementById("classic-result")?.classList.add("hidden");
        this.app.switchView("view-classic");
        this.render(data);
        this.connect();
    }

    async restoreSession() {
        let saved;
        try {
            saved = JSON.parse(sessionStorage.getItem("classicChessSession") || "null");
        } catch (error) {
            sessionStorage.removeItem("classicChessSession");
            return;
        }
        if (!saved?.roomCode || !saved?.playerId) return;
        try {
            const data = await this.request(
                `/classic/rooms/${encodeURIComponent(saved.roomCode)}`,
                { headers: { Authorization: `Bearer ${saved.playerId}` } }
            );
            this.enterRoom({ ...data, player_id: saved.playerId }, data.mode || saved.mode || "online");
        } catch (error) {
            sessionStorage.removeItem("classicChessSession");
        }
    }

    connect() {
        this.socketEnabled = false;
        if (this.socket) this.socket.close();
        this.socketEnabled = true;
        const url = window.CONFIG.getWsUrl();
        const socket = new WebSocket(
            `${url}/classic/${encodeURIComponent(this.roomCode)}`
        );
        this.socket = socket;
        socket.onopen = () => {
            if (this.socket !== socket) return;
            this.send({ type: "AUTH", player_id: this.playerId });
            clearInterval(this.pingInterval);
            this.pingInterval = setInterval(() => this.send({ type: "PING" }), 10000);
        };
        socket.onmessage = (event) => {
            if (this.socket !== socket) return;
            const data = JSON.parse(event.data);
            if (data.type === "PONG") {
                if (this.lastPingAt && data.server_time) {
                    this.serverClockOffset =
                        data.server_time * 1000 - (this.lastPingAt + Date.now()) / 2;
                }
                return;
            }
            if (data.type === "ERROR") {
                this.app.showToast(data.message, true);
                return;
            }
            if (data.players) this.players = data.players;
            if (data.game_state) this.render(data);
        };
        socket.onclose = () => {
            if (this.socket !== socket) return;
            clearInterval(this.pingInterval);
            if (this.socketEnabled) {
                clearTimeout(this.reconnectTimeout);
                this.reconnectTimeout = setTimeout(() => this.connect(), 2500);
            }
        };
        socket.onerror = () => {
            this.app.showToast("Classic chess connection interrupted. Reconnecting…", true);
        };
    }

    send(message) {
        if (this.socket?.readyState === WebSocket.OPEN) {
            if (message.type === "PING") this.lastPingAt = Date.now();
            this.socket.send(JSON.stringify(message));
        } else {
            this.app.showToast("Not connected. Reconnecting to the match…", true);
        }
    }

    render(data) {
        this.state = data.game_state || this.state;
        this.players = data.players || this.players;
        this.roomStatus = data.status || this.state?.status || this.roomStatus;
        this.serverStateAt = data.server_time ? data.server_time * 1000 : Date.now();
        this.updateServerClock(data.server_time);
        this.selectedSquare = null;
        if (!this.state) return;
        const status = data.status || this.state.status;
        const turnName = this.players[this.state.turn]?.name || this.state.turn;
        let label = status === "WAITING"
            ? (Object.keys(this.players).length === 2
                ? "Both players joined · waiting for the host to start…"
                : "Waiting for a second player to join…")
            : `${this.state.turn === "white" ? "White" : "Black"} (${turnName}) to move${this.state.in_check ? " — Check!" : ""}`;
        if (this.state.draw_offer && this.state.draw_offer !== this.mySide && this.mode === "online") {
            label = `${this.players[this.state.draw_offer]?.name || "Your opponent"} offered a draw`;
        }
        if (status === "COMPLETED") label = this.resultText();
        document.getElementById("classic-status").textContent = label;
        const isWaiting = status === "WAITING" && this.mode === "online";
        const isHost = this.players[this.mySide]?.host === true;
        const startButton = document.getElementById("classic-start-match");
        startButton.classList.toggle("hidden", !isWaiting || !isHost);
        startButton.disabled = Object.keys(this.players).length !== 2;
        document.getElementById("classic-ready").classList.toggle(
            "hidden", !isWaiting || isHost
        );
        document.getElementById("classic-leave-room").classList.toggle(
            "hidden", this.mode !== "online" || !isWaiting
        );
        if (isWaiting && !isHost) {
            const ready = this.players[this.mySide]?.ready === true;
            document.getElementById("classic-ready").textContent = ready ? "Cancel Ready" : "Ready";
        }
        document.getElementById("classic-white-name").textContent = this.players.white?.name || "White";
        document.getElementById("classic-black-name").textContent = this.players.black?.name || "Waiting for player";
        document.getElementById("classic-white-card").classList.toggle("active", status === "PLAYING" && this.state.turn === "white");
        document.getElementById("classic-black-card").classList.toggle("active", status === "PLAYING" && this.state.turn === "black");
        const drawOffer = this.state.draw_offer;
        const incomingDraw = drawOffer && (this.mode === "local" || drawOffer !== this.mySide);
        document.getElementById("classic-draw-actions").classList.toggle("hidden", !incomingDraw);
        document.getElementById("classic-offer-draw").disabled =
            status !== "PLAYING" || Boolean(drawOffer) || !this.state.last_mover ||
            (this.mode === "online" && this.state.last_mover !== this.mySide);
        document.getElementById("classic-claim-draw").disabled =
            status !== "PLAYING" || !this.state.can_claim_draw ||
            (this.mode === "online" && this.state.turn !== this.mySide);
        document.getElementById("classic-resign").disabled = status !== "PLAYING";
        this.renderBoard();
        this.renderHistory();
        this.renderCaptured();
        this.renderClocks();
        this.renderResult(status);
    }

    renderBoard() {
        const container = document.getElementById("classic-board");
        const ranks = this.state.fen.split(" ")[0].split("/");
        const board = [];
        for (let rankIndex = 0; rankIndex < 8; rankIndex++) {
            let file = 0;
            for (const cell of ranks[rankIndex]) {
                if (/\d/.test(cell)) {
                    file += Number(cell);
                } else {
                    board.push({ square: `${"abcdefgh"[file]}${8 - rankIndex}`, piece: cell });
                    file++;
                }
            }
        }
        const last = this.state.moves[this.state.moves.length - 1]?.uci;
        const lastSquares = last ? [last.slice(0, 2), last.slice(2, 4)] : [];
        const selectedMoves = this.state.legal_moves.filter(move => move.from === this.selectedSquare);
        const legalTargets = new Set(selectedMoves.map(move => move.to));
        const checkSquare = this.state.in_check
            ? board.find(item => item.piece === (this.state.turn === "white" ? "K" : "k"))?.square
            : null;
        const symbols = { K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
            k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" };
        let html = "";
        for (let rankIndex = 0; rankIndex < 8; rankIndex++) {
            for (let file = 0; file < 8; file++) {
                const squareName = `${"abcdefgh"[file]}${8 - rankIndex}`;
                const piece = board.find(item => item.square === squareName)?.piece;
                const classes = ["classic-square", (rankIndex + file) % 2 ? "dark" : "light"];
                if (this.selectedSquare === squareName) classes.push("selected");
                if (lastSquares.includes(squareName)) classes.push("last-move");
                if (squareName === checkSquare) classes.push("check");
                const marker = legalTargets.has(squareName)
                    ? `<span class="${piece ? "classic-legal-capture" : "classic-legal-dot"}"></span>`
                    : "";
                html += `<button type="button" class="${classes.join(" ")}" data-square="${squareName}" role="gridcell" aria-label="${squareName}${piece ? ` ${piece}` : ""}">
                    ${piece ? `<svg class="classic-piece ${piece === piece.toUpperCase() ? "white" : "black"}" viewBox="0 0 48 48" aria-hidden="true"><text x="50%" y="50%" dominant-baseline="central" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif" font-size="44">${symbols[piece]}</text></svg>` : ""}
                    ${marker}
                    ${file === 0 ? `<span class="classic-coordinate rank-label">${8 - rankIndex}</span>` : ""}
                    ${rankIndex === 7 ? `<span class="classic-coordinate file-label">${"abcdefgh"[file]}</span>` : ""}
                </button>`;
            }
        }
        container.innerHTML = html;
        container.querySelectorAll(".classic-piece").forEach(piece => {
            piece.style.width = "78%";
            piece.style.height = "78%";
        });
    }

    selectSquare(square) {
        if (!this.state || this.state.status !== "PLAYING") return;
        if (this.mode === "online" && this.mySide !== this.state.turn) return;
        if (this.selectedSquare && this.state.legal_moves.some(move =>
            move.from === this.selectedSquare && move.to === square
        )) {
            const choices = this.state.legal_moves.filter(move =>
                move.from === this.selectedSquare && move.to === square && move.promotion
            );
            let promotion = null;
            if (choices.length) {
                const choice = prompt("Promote pawn to queen, rook, bishop, or knight:", "queen");
                if (choice === null) return;
                const normalized = choice.trim().toLowerCase()[0];
                if (!["q", "r", "b", "n"].includes(normalized)) {
                    this.app.showToast("Choose queen, rook, bishop, or knight.", true);
                    return;
                }
                promotion = normalized;
            }
            this.send({ type: "MOVE", from: this.selectedSquare, to: square, promotion });
            this.selectedSquare = null;
            this.renderBoard();
            return;
        }
        const piece = this.pieceAt(square);
        const isCurrentSide = piece && (piece === piece.toUpperCase()) === (this.state.turn === "white");
        this.selectedSquare = isCurrentSide ? square : null;
        this.renderBoard();
    }

    pieceAt(square) {
        const ranks = this.state.fen.split(" ")[0].split("/");
        const fileTarget = square.charCodeAt(0) - 97;
        const rankIndex = 8 - Number(square[1]);
        let file = 0;
        for (const cell of ranks[rankIndex]) {
            if (/\d/.test(cell)) file += Number(cell);
            else {
                if (file === fileTarget) return cell;
                file++;
            }
        }
        return null;
    }

    renderHistory() {
        const list = document.getElementById("classic-move-history");
        const moves = this.state.moves || [];
        list.innerHTML = "";
        for (let index = 0; index < moves.length; index += 2) {
            const entry = document.createElement("li");
            entry.textContent = `${Math.floor(index / 2) + 1}. ${moves[index].san}${moves[index + 1] ? `  ${moves[index + 1].san}` : ""}`;
            list.appendChild(entry);
        }
        list.scrollTop = list.scrollHeight;
    }

    renderCaptured() {
        const symbol = { p: "♟", n: "♞", b: "♝", r: "♜", q: "♛" };
        document.getElementById("classic-captured-white").textContent =
            (this.state.captured?.white || []).map(piece => symbol[piece]).join("");
        document.getElementById("classic-captured-black").textContent =
            (this.state.captured?.black || []).map(piece => symbol[piece]).join("");
    }

    renderClocks() {
        if (!this.state?.clocks) return;
        for (const side of ["white", "black"]) {
            let seconds = this.state.clocks[side];
            if (seconds !== null && side === this.state.turn && this.roomStatus === "PLAYING") {
                const serverNow = Date.now() + (this.serverClockOffset || 0);
                seconds = Math.max(0, seconds - (serverNow - this.serverStateAt) / 1000);
            }
            document.getElementById(`classic-clock-${side}`).textContent =
                seconds === null ? "∞" : this.formatClock(seconds);
        }
    }

    updateServerClock(serverTime) {
        if (serverTime && this.serverClockOffset === null) {
            this.serverClockOffset = serverTime * 1000 - Date.now();
        }
    }

    formatClock(seconds) {
        const total = Math.ceil(seconds);
        const minutes = Math.floor(total / 60);
        const remainder = total % 60;
        return `${minutes}:${String(remainder).padStart(2, "0")}`;
    }

    resultText() {
        if (this.state.result === "1/2-1/2") return "Draw";
        if (this.state.result === "1-0") return "White wins";
        if (this.state.result === "0-1") return "Black wins";
        return "Game over";
    }

    renderResult(status) {
        const overlay = document.getElementById("classic-result");
        if (status !== "COMPLETED") {
            overlay.classList.add("hidden");
            return;
        }
        const labels = {
            checkmate: "by checkmate",
            stalemate: "by stalemate",
            insufficient_material: "by insufficient material",
            threefold_repetition: "by threefold repetition",
            fifty_moves: "by the fifty-move rule",
            resignation: "by resignation",
            timeout: "on time",
            agreement: "by agreement",
        };
        document.getElementById("classic-result-title").textContent = this.resultText();
        document.getElementById("classic-result-detail").textContent =
            labels[this.state.termination] || this.state.termination || "The game has ended.";
        overlay.classList.remove("hidden");
    }
}

window.ClassicChessUI = ClassicChessUI;
