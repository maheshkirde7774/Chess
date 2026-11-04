window.FOURX_AVATAR_ICONS = {
    king: "♔",
    queen: "♕",
    rook: "♖",
    bishop: "♗",
    knight: "♘",
    pawn: "♙",
    dragon: "🐉",
    phoenix: "🔥",
    cyber_cat: "🐈",
    royal_lion: "🦁",
    titan: "🛡️",
    oracle: "🔮",
    nebula_wolf: "🐺",
};

class FOURXProfile {
    constructor() {
        this.tokenKey = "fourx-device-profile-token";
        this.token = localStorage.getItem(this.tokenKey);
        this.profile = null;
        this.ready = this.initialize();
        this.bindEvents();
        window.addEventListener("fourx-premium-status", () => this.renderProfile());
    }

    authHeaders() {
        return this.token ? { Authorization: `Bearer ${this.token}` } : {};
    }

    async request(path, options = {}) {
        const response = await fetch(`${window.CONFIG.getServerUrl()}${path}`, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...this.authHeaders(),
                ...(options.headers || {}),
            },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Profile request failed");
        return data;
    }

    async initialize() {
        if (this.token) {
            try {
                this.profile = await this.request("/api/profile");
                if (!this.profile.timezone) {
                    this.profile = await this.request("/api/profile", {
                        method: "PATCH",
                        body: JSON.stringify({
                            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
                        }),
                    });
                }
                return this.profile;
            } catch (error) {
                if (!/credential/i.test(error.message) && !/401/.test(error.message)) throw error;
                localStorage.removeItem(this.tokenKey);
                this.token = null;
            }
        }
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
        const created = await this.request("/api/profile", {
            method: "POST",
            body: JSON.stringify({ timezone }),
        });
        this.token = created.access_token;
        this.profile = created.profile;
        localStorage.setItem(this.tokenKey, this.token);
        return this.profile;
    }

    bindEvents() {
        document.getElementById("profile-edit-form")?.addEventListener("submit", async (event) => {
            event.preventDefault();
            const username = document.getElementById("profile-username-input")?.value.trim();
            const avatar = document.querySelector("[data-profile-avatar].selected")?.dataset.profileAvatar;
            await this.update({ username, avatar });
        });
        document.querySelectorAll("[data-profile-avatar]").forEach((button) => {
            button.addEventListener("click", () => {
                document.querySelectorAll("[data-profile-avatar]").forEach(item => item.classList.remove("selected"));
                button.classList.add("selected");
            });
        });
        document.getElementById("profile-mode-filter")?.addEventListener("change", () => this.loadMatches());
        document.getElementById("profile-result-filter")?.addEventListener("change", () => this.loadMatches());
    }

    async update(changes) {
        try {
            await this.ready;
            this.profile = await this.request("/api/profile", {
                method: "PATCH",
                body: JSON.stringify(changes),
            });
            this.renderProfile();
            this.loadMatches();
            window.app?.showToast("Profile updated.");
        } catch (error) {
            window.app?.showToast(error.message, true);
        }
    }

    async refresh() {
        try {
            await this.ready;
            this.profile = await this.request("/api/profile");
            this.renderProfile();
            await this.loadMatches();
        } catch (error) {
            const notice = document.getElementById("profile-load-error");
            if (notice) {
                notice.textContent = `Profile could not be loaded: ${error.message}`;
                notice.classList.remove("hidden");
            }
        }
    }

    renderProfile() {
        const profile = this.profile;
        if (!profile) return;
        const avatarIcons = window.FOURX_AVATAR_ICONS;
        const setText = (id, value) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        };
        setText("profile-full-name", profile.username);
        const premiumAvatars = new Set(["titan", "oracle", "nebula_wolf"]);
        const avatar = premiumAvatars.has(profile.avatar)
            && window.FOURXSubscription?.premium !== true
            ? "knight"
            : profile.avatar;
        setText("profile-avatar-icon", avatarIcons[avatar] || avatarIcons.knight);
        setText("stat-total-games", profile.statistics.games);
        setText("stat-wins", profile.statistics.wins);
        setText("stat-losses", profile.statistics.losses);
        setText("stat-draws", profile.statistics.draws);
        setText("stat-winrate", `${profile.statistics.win_percentage}%`);
        setText("stat-streak", profile.statistics.current_streak);
        setText("stat-best-streak", profile.statistics.best_streak);
        setText("profile-classic-rating", profile.ratings.classic);
        setText("profile-four-rating", profile.ratings.four_player);
        setText("profile-level", profile.level);
        setText("profile-xp-label", `${profile.xp_into_level} / ${profile.xp_for_next_level} XP`);
        setText("profile-total-xp", `${profile.total_xp} total XP`);
        setText("profile-joined", profile.joined_at
            ? `Joined ${new Date(profile.joined_at).toLocaleDateString()}`
            : "New player");
        const progress = document.getElementById("profile-xp-progress");
        if (progress) {
            progress.max = profile.xp_for_next_level;
            progress.value = profile.xp_into_level;
        }
        const nameInput = document.getElementById("profile-username-input");
        if (nameInput && document.activeElement !== nameInput) nameInput.value = profile.username;
        document.querySelectorAll("[data-profile-avatar]").forEach(button => {
            button.classList.toggle("selected", button.dataset.profileAvatar === profile.avatar);
        });
        this.renderAchievements(profile.achievements || []);
    }

    renderAchievements(unlocked) {
        const definitions = [
            ["first_victory", "First Victory", "Win your first completed match.", "🏆"],
            ["ten_games", "10 Games Played", "Complete 10 verified matches.", "♟"],
            ["ten_wins", "10 Wins", "Win 10 verified matches.", "⚔"],
            ["five_streak", "On a Roll", "Win 5 matches in a row.", "🔥"],
            ["comeback", "Comeback Victory", "Win a Classic game after trailing by at least 3 material points.", "↩"],
            ["four_player_champion", "Four-Player Champion", "Win a Four-Player Chess match.", "👑"],
            ["chess_master", "Chess Master", "Reach a Classic Chess rating of 2000.", "♛"],
        ];
        const container = document.getElementById("profile-achievements");
        if (!container) return;
        container.replaceChildren();
        definitions.forEach(([key, title, description, icon]) => {
            const unlockedAt = unlocked.includes(key);
            const card = document.createElement("article");
            card.className = `achievement-badge-card${unlockedAt ? " unlocked" : ""}`;
            const mark = document.createElement("span");
            mark.className = "ach-icon";
            mark.textContent = icon;
            const detail = document.createElement("div");
            detail.className = "ach-meta";
            const name = document.createElement("strong");
            name.textContent = title;
            const help = document.createElement("small");
            help.textContent = unlockedAt ? "Unlocked" : description;
            detail.append(name, help);
            card.append(mark, detail);
            container.append(card);
        });
    }

    async loadMatches() {
        if (!this.token) return;
        const container = document.getElementById("profile-match-list");
        if (!container) return;
        container.replaceChildren();
        const mode = document.getElementById("profile-mode-filter")?.value || "";
        const result = document.getElementById("profile-result-filter")?.value || "";
        const query = new URLSearchParams();
        if (mode) query.set("game_mode", mode);
        if (result) query.set("result", result);
        try {
            await this.ready;
            const matches = await this.request(`/api/profile/matches?${query}`);
            if (matches.length === 0) {
                const empty = document.createElement("p");
                empty.className = "profile-empty";
                empty.textContent = "No completed matches yet. Unfinished or abandoned games are not recorded.";
                container.append(empty);
                return;
            }
            matches.forEach(match => {
                const row = document.createElement("article");
                row.className = "profile-match-row";
                const detail = document.createElement("div");
                const title = document.createElement("strong");
                title.textContent = `${match.game_mode === "classic" ? "Classic 1v1" : "Four-Player"} · ${match.result}`;
                const metadata = document.createElement("small");
                const when = new Date(match.completed_at).toLocaleString();
                metadata.textContent = `${match.opponents.join(", ") || "FOURX AI"} · ${when} · ${Math.floor(match.duration_seconds / 60)}m`;
                detail.append(title, metadata);
                const reward = document.createElement("span");
                const delta = match.rating_delta > 0 ? `+${match.rating_delta}` : `${match.rating_delta}`;
                reward.textContent = `${match.rated ? `${delta} rating · ` : ""}+${match.xp_awarded} XP`;
                reward.className = `profile-match-result ${match.result}`;
                row.append(detail, reward);
                if (match.moves?.length) {
                    const replay = document.createElement("details");
                    const summary = document.createElement("summary");
                    summary.textContent = "Move record";
                    const notation = document.createElement("p");
                    notation.textContent = match.moves.map(move =>
                        move.san || move.uci || (
                            move.from && move.to
                                ? `${JSON.stringify(move.from)} → ${JSON.stringify(move.to)}`
                                : ""
                        )
                    ).join(" ");
                    replay.append(summary, notation);
                    row.append(replay);
                }
                container.append(row);
            });
        } catch (error) {
            const notice = document.createElement("p");
            notice.className = "profile-empty error";
            notice.textContent = `Match history unavailable: ${error.message}`;
            container.append(notice);
        }
    }
}

window.FOURXProfile = new FOURXProfile();
