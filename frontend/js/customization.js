const CUSTOMIZATION_DEFAULTS = {
    board_theme: "classic_wood",
    piece_set: "staunton",
    sound: {
        enabled: true,
        volume: 0.65,
        events: {
            move: true,
            capture: true,
            check: true,
            checkmate: true,
            start: true,
            completion: true,
            notification: true,
            ui: true,
        },
    },
    animations: {
        movement: true,
        board_transition: true,
        move_highlighting: true,
        celebrations: true,
        reduced_motion: false,
    },
};

const CUSTOMIZATION_THEMES = [
    { id: "classic_wood", name: "Classic Wood", unlockXp: 0, colors: ["#d9b786", "#62432d"] },
    { id: "marble", name: "Marble", unlockXp: 0, colors: ["#e6e2dc", "#555d68"] },
    { id: "midnight", name: "Midnight", unlockXp: 100, colors: ["#b2bccb", "#27364b"] },
    { id: "ocean", name: "Ocean", unlockXp: 150, colors: ["#b8dce4", "#286179"] },
    { id: "emerald", name: "Emerald", unlockXp: 300, colors: ["#c4d7b8", "#315c46"] },
    { id: "royal_gold", name: "Royal Gold", unlockXp: 500, colors: ["#f0d7a1", "#7c5929"] },
    { id: "neon_cyber", name: "Neon Cyber", unlockXp: 800, colors: ["#b6c6ee", "#433370"] },
    { id: "minimal_light", name: "Minimal Light", unlockXp: 0, colors: ["#f2f1ed", "#626a73"] },
];

const CUSTOMIZATION_PIECE_SETS = [
    { id: "staunton", name: "Classic Staunton", unlockXp: 0, glyphs: ["♔", "♕", "♖", "♗", "♘", "♙"] },
    { id: "modern", name: "Modern", unlockXp: 0, glyphs: ["♔", "♕", "♖", "♗", "♘", "♙"] },
    { id: "minimal", name: "Minimal", unlockXp: 100, glyphs: ["♔", "♕", "♖", "♗", "♘", "♙"] },
    { id: "royal", name: "Royal", unlockXp: 300, glyphs: ["♔", "♕", "♖", "♗", "♘", "♙"] },
    { id: "futuristic", name: "Futuristic", unlockXp: 600, glyphs: ["♔", "♕", "♖", "♗", "♘", "♙"] },
];

const CUSTOMIZATION_AVATARS = [
    { id: "king", name: "King", icon: "♔", unlockXp: 0 },
    { id: "queen", name: "Queen", icon: "♕", unlockXp: 0 },
    { id: "rook", name: "Rook", icon: "♖", unlockXp: 0 },
    { id: "bishop", name: "Bishop", icon: "♗", unlockXp: 0 },
    { id: "knight", name: "Knight", icon: "♘", unlockXp: 0 },
    { id: "pawn", name: "Pawn", icon: "♙", unlockXp: 0 },
    { id: "dragon", name: "Dragon", icon: "🐉", unlockXp: 200 },
    { id: "phoenix", name: "Phoenix", icon: "🔥", unlockXp: 400 },
    { id: "cyber_cat", name: "Cyber Cat", icon: "🐈", unlockXp: 600 },
    { id: "royal_lion", name: "Royal Lion", icon: "🦁", unlockXp: 800 },
];

const CUSTOMIZATION_EVENT_LABELS = [
    ["move", "Piece movement"],
    ["capture", "Capture"],
    ["check", "Check"],
    ["checkmate", "Checkmate"],
    ["start", "Game start"],
    ["completion", "Game completion"],
    ["notification", "Notifications"],
    ["ui", "Interface clicks"],
];

const CUSTOMIZATION_ANIMATION_LABELS = [
    ["movement", "Piece movement animation"],
    ["board_transition", "Board transitions"],
    ["move_highlighting", "Last-move highlighting"],
    ["celebrations", "Celebration effects"],
    ["reduced_motion", "Reduced-motion mode"],
];

class FOURXCustomization {
    constructor() {
        this.storageKey = "fourx-customization-preferences";
        this.tab = "board";
        this.preferences = this.defaultPreferences();
        this.draft = this.defaultPreferences();
        this.avatar = "knight";
        this.draftAvatar = "knight";
        this.xp = 0;
        this.profileReady = false;
        this.hasLocalPreferences = false;
        this.statusMessage = "Preview changes, then apply to save them.";
        this.loadLocal();
        this.bindEvents();
        this.applyVisuals();
        this.loadProfilePreferences();
    }

    defaultPreferences() {
        return JSON.parse(JSON.stringify(CUSTOMIZATION_DEFAULTS));
    }

    normalizePreferences(value) {
        const defaults = this.defaultPreferences();
        const source = value && typeof value === "object" ? value : {};
        return {
            board_theme: source.board_theme || defaults.board_theme,
            piece_set: source.piece_set || defaults.piece_set,
            sound: {
                ...defaults.sound,
                ...(source.sound || {}),
                events: { ...defaults.sound.events, ...(source.sound?.events || {}) },
            },
            animations: { ...defaults.animations, ...(source.animations || {}) },
        };
    }

    loadLocal() {
        try {
            const stored = JSON.parse(localStorage.getItem(this.storageKey) || "null");
            if (stored) {
                this.hasLocalPreferences = Boolean(stored.preferences);
                this.preferences = this.normalizePreferences(stored.preferences);
                this.draft = this.normalizePreferences(stored.preferences);
                this.avatar = typeof stored.avatar === "string" ? stored.avatar : "knight";
                this.draftAvatar = this.avatar;
            }
        } catch (error) {
            console.error("Could not read local customization preferences.", error);
            this.statusMessage = "Local preferences could not be read; defaults are active.";
        }
    }

    async loadProfilePreferences() {
        try {
            await window.FOURXProfile?.ready;
            const profile = window.FOURXProfile?.profile;
            if (!profile || !window.FOURXProfile?.token) {
                this.statusMessage = "Using preferences saved on this device.";
                this.render();
                return;
            }
            this.xp = profile.total_xp || 0;
            const saved = await window.FOURXProfile.request("/api/profile/customization");
            const useLocalPreferences = saved.configured === false && this.hasLocalPreferences;
            const localAvatar = this.avatar;
            if (useLocalPreferences) {
                this.preferences = this.normalizePreferences(this.preferences);
                this.draft = this.normalizePreferences(this.preferences);
                await window.FOURXProfile.request("/api/profile/customization", {
                    method: "PUT",
                    body: JSON.stringify(this.preferences),
                });
                this.statusMessage = "Device preferences synchronized to your new profile.";
            } else {
                this.preferences = this.normalizePreferences(saved);
                this.draft = this.normalizePreferences(saved);
                this.statusMessage = "Profile preferences synchronized.";
            }
            this.avatar = useLocalPreferences ? localAvatar : (profile.avatar || "knight");
            if (useLocalPreferences && this.avatar !== profile.avatar) {
                window.FOURXProfile.profile = await window.FOURXProfile.request("/api/profile", {
                    method: "PATCH",
                    body: JSON.stringify({ avatar: this.avatar }),
                });
            }
            this.draftAvatar = this.avatar;
            this.profileReady = true;
            this.persistLocal();
            this.applyVisuals();
        } catch (error) {
            console.error("Could not synchronize profile customization.", error);
            this.statusMessage = `Profile sync unavailable: ${error.message}. Device preferences remain active.`;
        }
        this.render();
    }

    bindEvents() {
        document.getElementById("customization-tabs")?.addEventListener("click", event => {
            const tab = event.target.closest("[data-customization-tab]")?.dataset.customizationTab;
            if (!tab) return;
            this.tab = tab;
            this.render();
        });
        document.getElementById("customization-panel")?.addEventListener("click", event => {
            const choice = event.target.closest("[data-customization-choice]");
            if (!choice) return;
            const { kind, id } = choice.dataset;
            if (kind === "theme") this.draft.board_theme = id;
            if (kind === "piece") this.draft.piece_set = id;
            if (kind === "avatar") this.draftAvatar = id;
            this.applyVisuals(true);
            this.render();
        });
        document.getElementById("customization-panel")?.addEventListener("change", event => {
            const control = event.target;
            if (control.matches("[data-sound-setting]")) {
                const setting = control.dataset.soundSetting;
                if (setting === "enabled") this.draft.sound.enabled = control.checked;
                else this.draft.sound.events[setting] = control.checked;
                this.applyVisuals(true);
                this.render();
            } else if (control.matches("[data-animation-setting]")) {
                this.draft.animations[control.dataset.animationSetting] = control.checked;
                this.applyVisuals(true);
                this.render();
            }
        });
        document.getElementById("customization-panel")?.addEventListener("input", event => {
            const control = event.target;
            if (!control.matches("[data-sound-volume]")) return;
            this.draft.sound.volume = Number(control.value) / 100;
            const output = document.getElementById("customization-volume-value");
            if (output) output.textContent = `${control.value}%`;
            this.applyVisuals(true);
        });
        document.getElementById("customization-apply")?.addEventListener("click", () => this.apply());
        document.getElementById("customization-reset")?.addEventListener("click", () => this.reset());
        document.getElementById("customization-platform-settings")?.addEventListener("click", () => {
            window.app?.showModal("settings-modal");
        });
        document.getElementById("customization-back")?.addEventListener("click", () => {
            window.app?.switchView("view-home");
        });
    }

    isUnlocked(item) {
        return this.xp >= item.unlockXp;
    }

    createElement(tag, className, text) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    }

    createChoice(item, kind, selected, preview) {
        const unlocked = this.isUnlocked(item);
        const button = this.createElement(
            "button",
            `custom-choice${selected ? " selected" : ""}${unlocked ? "" : " locked"}`,
        );
        button.type = "button";
        button.dataset.customizationChoice = "true";
        button.dataset.kind = kind;
        button.dataset.id = item.id;
        button.setAttribute("aria-pressed", String(selected));
        if (preview) button.append(preview);
        button.append(this.createElement("strong", "", item.name));
        button.append(this.createElement(
            "small",
            "custom-choice-status",
            unlocked ? (selected ? "Selected" : "Unlocked") : `Unlock at ${item.unlockXp} XP`,
        ));
        return button;
    }

    renderBoardTab(panel) {
        panel.append(this.createElement("p", "customization-intro", "Choose a board palette. Every theme includes coordinated squares, borders, coordinates, and move indicators."));
        const grid = this.createElement("div", "custom-choice-grid");
        CUSTOMIZATION_THEMES.forEach(theme => {
            const swatches = this.createElement("span", "theme-swatches");
            theme.colors.forEach(color => {
                const square = this.createElement("i", "theme-swatch");
                square.style.backgroundColor = color;
                swatches.append(square);
            });
            grid.append(this.createChoice(
                theme, "theme", this.draft.board_theme === theme.id, swatches
            ));
        });
        panel.append(grid);
    }

    renderPiecesTab(panel) {
        panel.append(this.createElement("p", "customization-intro", "Scalable vector pieces keep their proportions across 8×8 and four-player boards."));
        const grid = this.createElement("div", "custom-choice-grid");
        CUSTOMIZATION_PIECE_SETS.forEach(set => {
            const preview = this.createElement("span", "piece-set-preview");
            set.glyphs.slice(0, 4).forEach(glyph => {
                preview.append(this.createElement("i", "", glyph));
            });
            grid.append(this.createChoice(
                set, "piece", this.draft.piece_set === set.id, preview
            ));
        });
        panel.append(grid);
    }

    renderAvatarsTab(panel) {
        panel.append(this.createElement("p", "customization-intro", "Choose a profile avatar. Earned XP unlocks additional collections; custom image uploads are not available because this project has no secure image-storage service."));
        const grid = this.createElement("div", "custom-choice-grid avatar-choice-grid");
        CUSTOMIZATION_AVATARS.forEach(avatar => {
            const preview = this.createElement("span", "avatar-choice-preview", avatar.icon);
            grid.append(this.createChoice(
                avatar, "avatar", this.draftAvatar === avatar.id, preview
            ));
        });
        panel.append(grid);
    }

    addSettingRow(container, label, key, checked, type) {
        const row = this.createElement("label", "custom-setting-row");
        const text = this.createElement("span", "", label);
        const input = this.createElement("input");
        input.type = "checkbox";
        input.checked = checked;
        input.dataset[type] = key;
        row.append(text, input);
        container.append(row);
    }

    renderSoundsTab(panel) {
        panel.append(this.createElement("p", "customization-intro", "Tune procedural Web Audio effects. Background music is not part of FOURX."));
        this.addSettingRow(panel, "Sound effects", "enabled", this.draft.sound.enabled, "soundSetting");
        const volume = this.createElement("label", "custom-volume-row");
        volume.append(this.createElement("span", "", "Master volume"));
        const range = this.createElement("input");
        range.type = "range";
        range.min = "0";
        range.max = "100";
        range.value = String(Math.round(this.draft.sound.volume * 100));
        range.dataset.soundVolume = "true";
        range.setAttribute("aria-label", "Master sound volume");
        const output = this.createElement("output", "", `${range.value}%`);
        output.id = "customization-volume-value";
        volume.append(range, output);
        panel.append(volume);
        panel.append(this.createElement("h3", "customization-subheading", "Sound events"));
        CUSTOMIZATION_EVENT_LABELS.forEach(([key, label]) => {
            this.addSettingRow(panel, label, key, this.draft.sound.events[key], "soundSetting");
        });
    }

    renderAnimationsTab(panel) {
        panel.append(this.createElement("p", "customization-intro", "Reduce visual motion without affecting move input, clocks, or game synchronization."));
        CUSTOMIZATION_ANIMATION_LABELS.forEach(([key, label]) => {
            this.addSettingRow(panel, label, key, this.draft.animations[key], "animationSetting");
        });
    }

    renderPreview() {
        const board = document.getElementById("customization-board-preview");
        if (!board) return;
        board.dataset.boardTheme = this.draft.board_theme;
        board.dataset.pieceSet = this.draft.piece_set;
        board.replaceChildren();
        const samplePieces = new Map([
            ["0,0", "♜"], ["0,4", "♚"], ["0,7", "♜"],
            ["1,1", "♟"], ["1,6", "♟"], ["6,1", "♙"], ["6,6", "♙"],
            ["7,0", "♖"], ["7,4", "♔"], ["7,7", "♖"],
        ]);
        for (let row = 0; row < 8; row++) {
            for (let column = 0; column < 8; column++) {
                const square = this.createElement(
                    "span",
                    `preview-square ${(row + column) % 2 ? "dark" : "light"}`,
                );
                const glyph = samplePieces.get(`${row},${column}`);
                if (glyph) {
                    square.append(this.createElement(
                        "i",
                        `preview-piece ${row < 2 ? "dark-piece" : "light-piece"}`,
                        glyph,
                    ));
                }
                if (row === 6 && column === 4) square.classList.add("preview-selected");
                if (row === 4 && column === 4) square.classList.add("preview-legal");
                board.append(square);
            }
        }
        const avatar = CUSTOMIZATION_AVATARS.find(item => item.id === this.draftAvatar);
        const icon = document.getElementById("customization-avatar-preview");
        if (icon) icon.textContent = avatar?.icon || "♘";
        const label = document.getElementById("customization-preview-label");
        if (label) {
            const theme = CUSTOMIZATION_THEMES.find(item => item.id === this.draft.board_theme);
            const pieces = CUSTOMIZATION_PIECE_SETS.find(item => item.id === this.draft.piece_set);
            label.textContent = `${theme?.name || "Board"} · ${pieces?.name || "Pieces"}`;
        }
    }

    render() {
        const tabs = document.getElementById("customization-tabs");
        const panel = document.getElementById("customization-panel");
        if (!tabs || !panel) return;
        tabs.querySelectorAll("[data-customization-tab]").forEach(button => {
            const selected = button.dataset.customizationTab === this.tab;
            button.classList.toggle("active", selected);
            button.setAttribute("aria-selected", String(selected));
        });
        panel.replaceChildren();
        const renderers = {
            board: () => this.renderBoardTab(panel),
            pieces: () => this.renderPiecesTab(panel),
            avatars: () => this.renderAvatarsTab(panel),
            sounds: () => this.renderSoundsTab(panel),
            animations: () => this.renderAnimationsTab(panel),
        };
        (renderers[this.tab] || renderers.board)();
        this.renderPreview();
        const theme = CUSTOMIZATION_THEMES.find(item => item.id === this.draft.board_theme);
        const pieces = CUSTOMIZATION_PIECE_SETS.find(item => item.id === this.draft.piece_set);
        const avatar = CUSTOMIZATION_AVATARS.find(item => item.id === this.draftAvatar);
        const locked = !theme || !pieces || !avatar
            || !this.isUnlocked(theme) || !this.isUnlocked(pieces) || !this.isUnlocked(avatar);
        const apply = document.getElementById("customization-apply");
        if (apply) apply.disabled = locked;
        const status = document.getElementById("customization-status");
        if (status) {
            status.textContent = locked
                ? `Preview only: earn ${Math.max(theme?.unlockXp || 0, pieces?.unlockXp || 0, avatar?.unlockXp || 0)} XP to unlock the selected item.`
                : this.statusMessage;
            status.classList.toggle("error", this.statusMessage.includes("unavailable") || this.statusMessage.includes("failed"));
        }
    }

    applyVisuals(previewOnly = false) {
        if (!previewOnly) {
            const root = document.getElementById("app-root");
            if (root) {
                root.dataset.boardTheme = this.preferences.board_theme;
                root.dataset.pieceSet = this.preferences.piece_set;
                const systemReduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false;
                root.dataset.reducedMotion = String(this.preferences.animations.reduced_motion || systemReduced);
                root.dataset.boardTransition = String(this.preferences.animations.board_transition);
                root.dataset.moveHighlighting = String(this.preferences.animations.move_highlighting);
                root.dataset.celebrations = String(this.preferences.animations.celebrations);
            }
            window.soundSystem?.applyPreferences(this.preferences.sound);
            const soundToggle = document.getElementById("sound-toggle-chk");
            if (soundToggle) soundToggle.checked = this.preferences.sound.enabled;
            window.app?.updateSoundIcon(this.preferences.sound.enabled);
        }
        const previewBoard = document.getElementById("customization-board-preview");
        if (previewBoard) {
            previewBoard.dataset.boardTheme = this.draft.board_theme;
            previewBoard.dataset.pieceSet = this.draft.piece_set;
        }
    }

    persistLocal() {
        localStorage.setItem(this.storageKey, JSON.stringify({
            preferences: this.preferences,
            avatar: this.avatar,
        }));
    }

    async apply() {
        const theme = CUSTOMIZATION_THEMES.find(item => item.id === this.draft.board_theme);
        const pieces = CUSTOMIZATION_PIECE_SETS.find(item => item.id === this.draft.piece_set);
        const avatar = CUSTOMIZATION_AVATARS.find(item => item.id === this.draftAvatar);
        if (!theme || !pieces || !avatar || !this.isUnlocked(theme)
            || !this.isUnlocked(pieces) || !this.isUnlocked(avatar)) return;

        this.preferences = this.normalizePreferences(this.draft);
        this.avatar = this.draftAvatar;
        try {
            this.persistLocal();
            this.applyVisuals();
        } catch (error) {
            this.statusMessage = `Could not save preferences on this device: ${error.message}`;
            console.error(this.statusMessage, error);
            this.render();
            return;
        }
        try {
            await window.FOURXProfile?.ready;
            if (window.FOURXProfile?.token) {
                await window.FOURXProfile.request("/api/profile/customization", {
                    method: "PUT",
                    body: JSON.stringify(this.preferences),
                });
                const profile = await window.FOURXProfile.request("/api/profile", {
                    method: "PATCH",
                    body: JSON.stringify({ avatar: this.avatar }),
                });
                window.FOURXProfile.profile = profile;
                window.FOURXProfile.renderProfile();
                this.profileReady = true;
                this.xp = profile.total_xp || this.xp;
                this.statusMessage = "Preferences saved on this device and synchronized to your profile.";
            } else {
                this.statusMessage = "Preferences saved on this device.";
            }
        } catch (error) {
            this.statusMessage = `Saved on this device, but profile sync failed: ${error.message}`;
            console.error("Could not save profile customization.", error);
        }
        this.applyVisuals();
        this.render();
    }

    async reset() {
        this.draft = this.defaultPreferences();
        this.draftAvatar = "knight";
        this.applyVisuals(true);
        await this.apply();
    }

    onSoundEnabledChanged(enabled) {
        this.preferences.sound.enabled = enabled;
        this.draft.sound.enabled = enabled;
        try {
            this.persistLocal();
            this.statusMessage = "Sound preference saved on this device.";
        } catch (error) {
            this.statusMessage = `Could not save sound preference: ${error.message}`;
            console.error(this.statusMessage, error);
        }
        if (this.profileReady) {
            window.FOURXProfile.request("/api/profile/customization", {
                method: "PUT",
                body: JSON.stringify(this.preferences),
            }).then(() => {
                this.statusMessage = "Sound preference synchronized to your profile.";
                this.render();
            }).catch(error => {
                this.statusMessage = `Sound preference saved locally; profile sync failed: ${error.message}`;
                console.error("Could not synchronize sound preference.", error);
                this.render();
            });
        }
        this.render();
    }

    async onOpen() {
        this.draft = this.normalizePreferences(this.preferences);
        this.draftAvatar = this.avatar;
        this.applyVisuals();
        this.render();
        if (!this.profileReady) return;
        try {
            const [profile, saved] = await Promise.all([
                window.FOURXProfile.request("/api/profile"),
                window.FOURXProfile.request("/api/profile/customization"),
            ]);
            this.xp = profile.total_xp || 0;
            this.avatar = profile.avatar || "knight";
            this.draftAvatar = this.avatar;
            this.preferences = this.normalizePreferences(saved);
            this.draft = this.normalizePreferences(saved);
            window.FOURXProfile.profile = profile;
            this.statusMessage = "Profile preferences synchronized.";
            this.persistLocal();
            this.applyVisuals();
        } catch (error) {
            this.statusMessage = `Profile sync unavailable: ${error.message}. Device preferences remain active.`;
            console.error("Could not refresh customization profile state.", error);
        }
        this.render();
    }
}

window.FOURXCustomization = new FOURXCustomization();
