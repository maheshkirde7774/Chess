/**
 * Neon Four Chess - WebSocket Client
 * Real-time room synchronization, connection resilience, and event dispatching.
 */

class WebSocketClient {
    constructor(onMessageCallback, onStatusCallback) {
        this.ws = null;
        this.roomCode = null;
        this.playerId = null;
        this.onMessageCallback = onMessageCallback;
        this.onStatusCallback = onStatusCallback;
        this.pingInterval = null;
        this.reconnectTimeout = null;
        this.isExplicitlyClosed = false;
    }

    connect(roomCode, playerId) {
        this.isExplicitlyClosed = false;
        this.roomCode = roomCode.toUpperCase();
        this.playerId = playerId;

        const baseWs = window.CONFIG.getWsUrl();
        const wsUrl = `${baseWs}/${this.roomCode}`;

        if (this.ws) {
            try { this.ws.close(); } catch(e) {}
        }

        console.log(`Connecting to room ${this.roomCode}`);
        if (this.onStatusCallback) this.onStatusCallback("CONNECTING");

        try {
            const socket = new WebSocket(wsUrl);
            this.ws = socket;
            socket.onopen = () => {
                if (this.ws !== socket) return;
                console.log("WebSocket connected successfully!");
                if (this.onStatusCallback) this.onStatusCallback("CONNECTED");

                this.send({ type: "AUTH", player_id: this.playerId });
                if (this.pingInterval) clearInterval(this.pingInterval);
                this.pingInterval = setInterval(() => {
                    this.send({ type: "PING" });
                }, 15000);
            };

            socket.onmessage = (event) => {
                if (this.ws !== socket) return;
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === "PONG") return;
                    if (this.onMessageCallback) this.onMessageCallback(data);
                } catch (err) {
                    console.error("Error parsing WebSocket message:", err);
                }
            };

            socket.onerror = (err) => {
                if (this.ws !== socket) return;
                console.warn("WebSocket error:", err);
                if (this.onStatusCallback) this.onStatusCallback("ERROR");
            };

            socket.onclose = () => {
                if (this.ws !== socket) return;
                console.log("WebSocket closed");
                if (this.pingInterval) clearInterval(this.pingInterval);
                if (this.onStatusCallback) this.onStatusCallback("DISCONNECTED");

                if (!this.isExplicitlyClosed) this._scheduleReconnect();
            };
        } catch (e) {
            console.error("WebSocket initialization failed:", e);
            this._scheduleReconnect();
            return;
        }
    }

    _scheduleReconnect() {
        if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = setTimeout(() => {
            if (!this.isExplicitlyClosed && this.roomCode && this.playerId) {
                console.log("Attempting WebSocket reconnection...");
                this.connect(this.roomCode, this.playerId);
            }
        }, 3000);
    }

    send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        } else {
            console.warn("Cannot send message, WebSocket is not open.");
        }
    }

    disconnect() {
        this.isExplicitlyClosed = true;
        if (this.pingInterval) clearInterval(this.pingInterval);
        if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
        if (this.ws) {
            try { this.ws.close(); } catch(e) {}
            this.ws = null;
        }
    }
}

window.WebSocketClient = WebSocketClient;
