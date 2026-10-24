/**
 * Neon Four Chess - Network & Configuration
 * Provides configurable API and WebSocket endpoints for Local, Web, and Android Capacitor environments.
 */

const CONFIG = {
    // Default server address detection:
    // If running in browser hosted by backend, use window.location
    // If running in Capacitor/Android, use stored LAN URL or fallback to user-configured IP
    getDefaultServerUrl() {
        const stored = localStorage.getItem("neon_chess_backend_url");
        if (stored) return stored;

        // If hosted on a web server (e.g. port 8000)
        if (typeof window !== "undefined" && window.location.hostname && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
            return `${window.location.protocol}//${window.location.host}`;
        }

        // Default local dev server
        return "http://localhost:8000";
    },

    getServerUrl() {
        return localStorage.getItem("neon_chess_backend_url") || this.getDefaultServerUrl();
    },

    setServerUrl(url) {
        if (!url) return;
        let clean = url.trim().replace(/\/+$/, "");
        if (!clean.startsWith("http://") && !clean.startsWith("https://")) {
            clean = "http://" + clean;
        }
        localStorage.setItem("neon_chess_backend_url", clean);
    },

    getWsUrl() {
        const httpUrl = this.getServerUrl();
        const wsProto = httpUrl.startsWith("https://") ? "wss://" : "ws://";
        const hostPath = httpUrl.replace(/^https?:\/\//, "");
        return `${wsProto}${hostPath}/ws`;
    },

    // Audio preferences
    isAudioEnabled() {
        const val = localStorage.getItem("neon_chess_sound");
        return val === null ? true : val === "true";
    },

    setAudioEnabled(enabled) {
        localStorage.setItem("neon_chess_sound", enabled ? "true" : "false");
    },

    // Pass device prompt in local mode
    isPassPromptEnabled() {
        const val = localStorage.getItem("neon_chess_pass_prompt");
        return val === null ? false : val === "true"; // default off for snappy local play, can be enabled
    },

    setPassPromptEnabled(enabled) {
        localStorage.setItem("neon_chess_pass_prompt", enabled ? "true" : "false");
    },

    // Auto rotate board to active player in local mode
    isAutoRotateEnabled() {
        const val = localStorage.getItem("neon_chess_auto_rotate");
        return val === null ? false : val === "true";
    },

    setAutoRotateEnabled(enabled) {
        localStorage.setItem("neon_chess_auto_rotate", enabled ? "true" : "false");
    }
};

window.CONFIG = CONFIG;
