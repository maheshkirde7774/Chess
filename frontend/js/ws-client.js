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
        const wsUrl = `${baseWs}/${this.roomCode}?player_id=${encodeURIComponent(this.playerId)}`;

        if (this.ws) {
            try { this.ws.close(); } catch(e) {}
        }

        console.log(`Connecting to WebSocket: ${wsUrl}`);
        if (this.onStatusCallback) this.onStatusCallback("CONNECTING");

        try {
            this.ws = new WebSocket(wsUrl);
        } catch (e) {
            console.error("WebSocket initialization failed:", e);
            this._scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            console.log("WebSocket connected successfully!");
            if (this.onStatusCallback) this.onStatusCallback("CONNECTED");

            // Start heartbeat ping
            if (this.pingInterval) clearInterval(this.pingInterval);
            this.pingInterval = setInterval(() => {
                this.send({ type: "PING" });
            }, 15000);
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "PONG") return; // Heartbeat response
                if (this.onMessageCallback) {
                    this.onMessageCallback(data);
                }
            } catch (err) {
                console.error("Error parsing WebSocket message:", err);
            }
        };

        this.ws.onerror = (err) => {
            console.warn("WebSocket error:", err);
            if (this.onStatusCallback) this.onStatusCallback("ERROR");
        };

        this.ws.onclose = () => {
            console.log("WebSocket closed");
            if (this.pingInterval) clearInterval(this.pingInterval);
            if (this.onStatusCallback) this.onStatusCallback("DISCONNECTED");

            if (!this.isExplicitlyClosed) {
                this._scheduleReconnect();
            }
        };
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
