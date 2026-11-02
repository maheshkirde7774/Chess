class FOURXSocialController {
    constructor(app) {
        this.app = app;
        this.dashboard = null;
        this.conversationId = null;
        this.conversationPlayer = null;
        this.socket = null;
        this.pingInterval = null;
        this.reconnectTimeout = null;
        this.searchTimeout = null;
        this.lastActivitySentAt = 0;
        this.seenNotifications = new Set();
        this.bindEvents();
        this.connect();
    }

    async request(path, options = {}) {
        await window.FOURXProfile.ready;
        const response = await fetch(`${window.CONFIG.getServerUrl()}${path}`, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                ...window.FOURXProfile.authHeaders(),
                ...(options.headers || {}),
            },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Social request failed");
        return data;
    }

    bindEvents() {
        document.getElementById("social-search-form")?.addEventListener("submit", (event) => {
            event.preventDefault();
            this.searchPlayers();
        });
        document.getElementById("social-player-search")?.addEventListener("input", () => {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(() => this.searchPlayers(), 250);
        });
        document.getElementById("social-search-results")?.addEventListener("click", (event) => {
            this.handleAction(event);
        });
        document.getElementById("social-search-results")?.addEventListener("click", (event) => {
            const profileButton = event.target.closest("[data-social-profile]");
            if (profileButton) this.showProfilePreview(profileButton.dataset.socialProfile);
        });
        document.getElementById("friends-list-container")?.addEventListener("click", (event) => {
            const profileButton = event.target.closest("[data-social-profile]");
            if (profileButton) {
                this.showProfilePreview(profileButton.dataset.socialProfile);
                return;
            }
            this.handleAction(event);
        });
        document.getElementById("social-online-friends-list")?.addEventListener("click", (event) => {
            const profileButton = event.target.closest("[data-social-profile]");
            if (profileButton) {
                this.showProfilePreview(profileButton.dataset.socialProfile);
                return;
            }
            this.handleAction(event);
        });
        [
            "social-incoming-requests",
            "social-outgoing-requests",
            "social-invitations",
            "social-notifications",
        ].forEach((id) => {
            document.getElementById(id)?.addEventListener("click", (event) => this.handleAction(event));
        });
        document.getElementById("social-chat-list")?.addEventListener("click", (event) => {
            const row = event.target.closest("[data-conversation-id]");
            if (row) this.openConversation(row.dataset.conversationId, row.dataset.playerId);
        });
        document.getElementById("social-message-form")?.addEventListener("submit", (event) => {
            event.preventDefault();
            this.sendMessage();
        });
        document.querySelectorAll("[data-social-emoji]").forEach((button) => {
            button.addEventListener("click", () => {
                const input = document.getElementById("social-message-input");
                if (!input) return;
                input.value += button.dataset.socialEmoji || "";
                input.focus();
            });
        });
        document.getElementById("social-mark-notifications-read")?.addEventListener("click", () => {
            this.runAction(async () => {
                await this.request("/api/social/notifications/read", { method: "POST" });
                await this.refreshDashboard();
            });
        });
        const sendActivity = () => {
            const now = Date.now();
            if (now - this.lastActivitySentAt < 30000) return;
            this.lastActivitySentAt = now;
            this.sendSocket({ type: "ACTIVITY" });
        };
        window.addEventListener("pointerdown", sendActivity, { passive: true });
        window.addEventListener("keydown", sendActivity);
    }

    async onViewEntered() {
        await this.refreshDashboard();
    }

    async refreshDashboard() {
        try {
            this.dashboard = await this.request("/api/social/dashboard");
            this.renderDashboard();
        } catch (error) {
            const friends = document.getElementById("friends-list-container");
            if (friends) friends.textContent = `Social dashboard unavailable: ${error.message}`;
            this.app.showToast(error.message, true);
        }
    }

    async searchPlayers() {
        const input = document.getElementById("social-player-search");
        const results = document.getElementById("social-search-results");
        if (!input || !results) return;
        const query = input.value.trim();
        results.replaceChildren();
        if (query.length < 2) {
            if (query.length) results.append(this.emptyRow("Enter at least 2 characters to search."));
            return;
        }
        results.textContent = "Searching FOURX players…";
        try {
            const players = await this.request(`/api/social/players?q=${encodeURIComponent(query)}`);
            results.replaceChildren();
            if (!players.length) {
                results.append(this.emptyRow("No matching players found."));
                return;
            }
            players.forEach((player) => {
                const row = this.playerRow(player);
                row.append(
                    this.button("Add friend", "request", player.id, "primary"),
                    this.button("Block", "block", player.id),
                    this.button("Report", "report", player.id)
                );
                results.append(row);
            });
        } catch (error) {
            results.replaceChildren(this.emptyRow(error.message, true));
        }
    }

    renderDashboard() {
        const data = this.dashboard;
        if (!data) return;
        const friends = document.getElementById("friends-list-container");
        const summary = document.getElementById("social-friends-summary");
        if (summary) {
            const online = data.friends.filter((friend) => friend.status !== "offline").length;
            summary.textContent = `${data.friends.length} friend${data.friends.length === 1 ? "" : "s"} · ${online} online`;
        }
        if (friends) {
            friends.replaceChildren();
            if (!data.friends.length) {
                friends.append(this.emptyRow("Your list is empty. Search for players above to add friends."));
            }
            data.friends.forEach((friend) => {
                friends.append(this.friendRow(friend, true));
            });
        }
        const onlineFriends = document.getElementById("social-online-friends-list");
        if (onlineFriends) {
            onlineFriends.replaceChildren();
            const activeFriends = data.friends.filter((friend) => friend.status !== "offline");
            if (!activeFriends.length) {
                onlineFriends.append(this.emptyRow("No friends are online right now."));
            }
            activeFriends.forEach((friend) => onlineFriends.append(this.friendRow(friend, false)));
        }
        this.renderRequests("social-incoming-requests", data.incoming_requests, "incoming");
        this.renderRequests("social-outgoing-requests", data.outgoing_requests, "outgoing");
        this.renderBlockedPlayers(data.blocked_players || []);
        this.renderConversations(data.conversations);
        this.renderInvitations(data.invitations);
        this.renderNotifications(data.notifications);
        const navBadge = document.getElementById("social-notification-count");
        if (navBadge) {
            navBadge.textContent = data.unread_notifications ? String(data.unread_notifications) : "";
            navBadge.classList.toggle("hidden", !data.unread_notifications);
        }
        if (this.conversationId && !data.conversations.some((item) => item.id === this.conversationId)) {
            this.closeConversation();
        }
    }

    renderRequests(containerId, requests, direction) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.replaceChildren();
        if (!requests.length) {
            container.append(this.emptyRow(direction === "incoming" ? "No incoming requests." : "No outgoing requests."));
            return;
        }

        requests.forEach((request) => {
            if (!request.player) return;
            const row = this.playerRow(request.player);
            if (direction === "incoming") {
                row.append(
                    this.button("Accept", "accept-request", request.id, "primary"),
                    this.button("Reject", "reject-request", request.id)
                );
            } else {
                row.append(this.button("Cancel", "cancel-request", request.id));
            }
            container.append(row);
        });
    }

    friendRow(friend, includeManagement) {
        const row = this.playerRow(friend);
        row.append(
            this.button("Message", "chat", friend.id, "primary"),
            this.button("1v1", "invite-classic", friend.id),
            this.button("4-player", "invite-four", friend.id)
        );
        if (includeManagement) {
            row.append(
                this.button("Remove", "remove", friend.id),
                this.button("Block", "block", friend.id),
                this.button("Report", "report", friend.id)
            );
        }
        return row;
    }

    renderBlockedPlayers(players) {
        const container = document.getElementById("social-blocked-players");
        if (!container) return;
        container.replaceChildren();
        if (!players.length) {
            container.append(this.emptyRow("No blocked players."));
            return;
        }
        players.forEach((player) => {
            const row = this.playerRow(player);
            row.append(this.button("Unblock", "unblock", player.id));
            container.append(row);
        });
    }

    renderConversations(conversations) {
        const list = document.getElementById("social-chat-list");
        if (!list) return;
        list.replaceChildren();
        if (!conversations.length) {
            list.append(this.emptyRow("Chats with friends appear here."));
            this.closeConversation();
            return;
        }
        conversations.forEach((conversation) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `social-chat-entry${conversation.id === this.conversationId ? " selected" : ""}`;
            button.dataset.conversationId = conversation.id;
            button.dataset.playerId = conversation.player.id;
            const title = document.createElement("span");
            title.className = "social-chat-entry-title";
            title.textContent = conversation.player.username;
            const status = document.createElement("span");
            status.className = `social-status social-status-${conversation.player.status}`;
            status.textContent = conversation.player.status;
            const preview = document.createElement("span");
            preview.className = "social-chat-preview";
            preview.textContent = conversation.last_message?.content || "Start a conversation";
            const line = document.createElement("span");
            line.className = "social-chat-entry-top";
            line.append(title, status);
            button.append(line, preview);
            if (conversation.unread) {
                const unread = document.createElement("span");
                unread.className = "social-unread-badge";
                unread.textContent = String(conversation.unread);
                button.append(unread);
            }
            list.append(button);
        });
    }

    renderInvitations(invitations) {
        const container = document.getElementById("social-invitations");
        if (!container) return;
        container.replaceChildren();
        if (!invitations.length) {
            container.append(this.emptyRow("No pending game invitations."));
            return;
        }
        invitations.forEach((invite) => {
            if (!invite.player) return;
            const row = document.createElement("div");
            row.className = "social-list-row";
            const title = document.createElement("strong");
            title.textContent = `${invite.player.username} · ${invite.game_mode === "classic" ? "Classic 1v1" : "Four-Player Chess"}`;
            const note = document.createElement("span");
            note.className = "social-row-note";
            note.textContent = invite.direction === "incoming" ? "Invited you to play" : "Waiting for a response";
            row.append(title, note);
            if (invite.direction === "incoming") {
                row.append(
                    this.button("Accept", "accept-invitation", invite.id, "primary"),
                    this.button("Reject", "reject-invitation", invite.id)
                );
            } else {
                row.append(this.button("Cancel", "cancel-invitation", invite.id));
            }
            container.append(row);
        });
    }

    renderNotifications(notifications) {
        const container = document.getElementById("social-notifications");
        if (!container) return;
        container.replaceChildren();
        if (!notifications.length) {
            container.append(this.emptyRow("You're all caught up."));
            return;
        }
        notifications.forEach((notification) => {
            const row = document.createElement("div");
            row.className = `social-notification${notification.read_at ? "" : " unread"}`;
            const actor = notification.actor?.username || "FOURX";
            const description = {
                friend_request: `${actor} sent you a friend request.`,
                friend_accepted: `${actor} accepted your friend request.`,
                new_message: `${actor}: ${notification.payload.preview || "sent you a message"}`,
                game_invitation: `${actor} invited you to ${notification.payload.game_mode === "classic" ? "Classic 1v1" : "Four-Player Chess"}.`,
                invitation_accepted: `${actor} accepted your game invitation.`,
                invitation_rejected: `${actor} declined your game invitation.`,
            }[notification.type] || "You have a new FOURX update.";
            const text = document.createElement("span");
            text.textContent = description;
            row.append(text);
            if (notification.type === "new_message" && notification.payload.conversation_id) {
                row.append(this.button("Open chat", "open-chat", notification.payload.conversation_id));
            }
            if (notification.type === "invitation_accepted" && notification.payload.room_code) {
                row.append(this.button("Join match", "join-notification-game", notification.id));
            }
            container.append(row);
        });
    }

    playerRow(player) {
        const row = document.createElement("div");
        row.className = "social-list-row";
        row.dataset.playerId = player.id;
        const name = document.createElement("button");
        name.type = "button";
        name.className = "social-player-name";
        name.dataset.socialProfile = player.username;
        name.textContent = player.username;
        const status = document.createElement("span");
        status.className = `social-status social-status-${player.status || "offline"}`;
        status.textContent = player.status || "offline";
        row.append(name, status);
        return row;
    }

    button(label, action, value, variant = "") {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `mini-action-btn social-action${variant ? ` ${variant}` : ""}`;
        button.dataset.socialAction = action;
        if (["accept-request", "reject-request", "cancel-request"].includes(action)) button.dataset.requestId = value;
        else if (action.includes("invitation")) button.dataset.invitationId = value;
        else if (action === "open-chat") button.dataset.conversationId = value;
        else if (action === "join-notification-game") button.dataset.notificationId = value;
        else button.dataset.playerId = value;
        button.textContent = label;
        return button;
    }

    emptyRow(text, error = false) {
        const row = document.createElement("p");
        row.className = `social-empty${error ? " error" : ""}`;
        row.textContent = text;
        return row;
    }

    async showProfilePreview(username) {
        const container = document.getElementById("social-profile-preview");
        if (!container) return;
        container.textContent = "Loading player profile…";
        container.classList.remove("hidden");
        try {
            const profile = await this.request(`/api/players/${encodeURIComponent(username)}`);
            container.replaceChildren();
            const title = document.createElement("strong");
            title.textContent = profile.username;
            const details = document.createElement("p");
            details.textContent = `Level ${profile.level} · ${profile.games} games · ${profile.win_percentage}% wins`;
            const ratings = document.createElement("p");
            ratings.textContent = `Classic ${profile.ratings.classic} · Four-Player ${profile.ratings.four_player}`;
            container.append(title, details, ratings);
        } catch (error) {
            container.textContent = `Profile preview unavailable: ${error.message}`;
        }
    }

    async handleAction(event) {
        const button = event.target.closest("[data-social-action]");
        if (!button) return;
        const action = button.dataset.socialAction;
        const playerId = button.dataset.playerId;
        await this.runAction(async () => {
            if (action === "request") {
                await this.request("/api/social/requests", {
                    method: "POST", body: JSON.stringify({ player_id: playerId }),
                });
            } else if (action === "accept-request") {
                await this.request(`/api/social/requests/${button.dataset.requestId}/accept`, { method: "POST" });
            } else if (action === "reject-request") {
                await this.request(`/api/social/requests/${button.dataset.requestId}/reject`, { method: "POST" });
            } else if (action === "cancel-request") {
                await this.request(`/api/social/requests/${button.dataset.requestId}`, { method: "DELETE" });
            } else if (action === "remove") {
                if (!window.confirm("Remove this friend? Existing chat history will remain private but unavailable.")) return;
                await this.request(`/api/social/friends/${encodeURIComponent(playerId)}`, { method: "DELETE" });
            } else if (action === "block") {
                if (!window.confirm("Block this player? This removes the friendship and prevents chat and invitations.")) return;
                await this.request(`/api/social/blocks/${encodeURIComponent(playerId)}`, { method: "POST" });
            } else if (action === "unblock") {
                await this.request(`/api/social/blocks/${encodeURIComponent(playerId)}`, { method: "DELETE" });
            } else if (action === "report") {
                await this.request("/api/social/reports", {
                    method: "POST",
                    body: JSON.stringify({ player_id: playerId, category: "other", details: "" }),
                });
                this.app.showToast("Report submitted.");
            } else if (action === "chat") {
                await this.openChatForPlayer(playerId);
                return;
            } else if (action === "invite-classic" || action === "invite-four") {
                const gameMode = action === "invite-classic" ? "classic" : "four_player";
                await this.request("/api/social/invitations", {
                    method: "POST",
                    body: JSON.stringify({ player_id: playerId, game_mode: gameMode }),
                });
                this.app.showToast("Game invitation sent.");
            } else if (action === "accept-invitation") {
                const result = await this.request(
                    `/api/social/invitations/${button.dataset.invitationId}/accept`,
                    { method: "POST" }
                );
                await this.app.joinSocialInvitation(result.launch);
            } else if (action === "reject-invitation") {
                await this.request(`/api/social/invitations/${button.dataset.invitationId}/reject`, { method: "POST" });
            } else if (action === "cancel-invitation") {
                await this.request(`/api/social/invitations/${button.dataset.invitationId}`, { method: "DELETE" });
            } else if (action === "open-chat") {
                await this.openConversation(button.dataset.conversationId);
                return;
            } else if (action === "join-notification-game") {
                const notification = this.dashboard?.notifications.find(
                    (item) => String(item.id) === button.dataset.notificationId
                );
                if (notification?.payload) await this.app.joinSocialInvitation({
                    game_mode: notification.payload.game_mode,
                    ...notification.payload,
                });
            }
            await this.refreshDashboard();
        });
    }

    async runAction(action) {
        try {
            await action();
        } catch (error) {
            this.app.showToast(error.message, true);
        }
    }

    async openChatForPlayer(playerId) {
        const conversation = await this.request(`/api/social/conversations/${encodeURIComponent(playerId)}`, {
            method: "POST",
        });
        await this.openConversation(conversation.id, playerId);
    }

    async openConversation(conversationId, playerId = null) {
        this.conversationId = conversationId;
        const conversation = this.dashboard?.conversations.find((item) => item.id === conversationId);
        this.conversationPlayer = conversation?.player || null;
        if (playerId && !this.conversationPlayer) {
            this.conversationPlayer = this.dashboard?.friends.find((item) => item.id === playerId) || null;
        }
        document.getElementById("social-chat-empty")?.classList.add("hidden");
        document.getElementById("social-chat-active")?.classList.remove("hidden");
        await this.loadMessages();
        await this.request(`/api/social/conversations/${encodeURIComponent(conversationId)}/read`, {
            method: "POST",
        });
        await this.refreshDashboard();
    }

    closeConversation() {
        this.conversationId = null;
        this.conversationPlayer = null;
        document.getElementById("social-chat-empty")?.classList.remove("hidden");
        document.getElementById("social-chat-active")?.classList.add("hidden");
    }

    async loadMessages() {
        if (!this.conversationId) return;
        const data = await this.request(
            `/api/social/conversations/${encodeURIComponent(this.conversationId)}/messages`
        );
        const header = document.getElementById("social-chat-header");
        const messages = document.getElementById("social-chat-messages");
        if (!header || !messages) return;
        header.replaceChildren();
        const name = document.createElement("strong");
        name.textContent = this.conversationPlayer?.username || "FOURX friend";
        const status = document.createElement("span");
        status.className = `social-status social-status-${this.conversationPlayer?.status || "offline"}`;
        status.textContent = this.conversationPlayer?.status || "offline";
        header.append(name, status);
        messages.replaceChildren();
        if (!data.messages.length) {
            messages.append(this.emptyRow("No messages yet. Send the first hello."));
        }
        data.messages.forEach((message) => {
            const bubble = document.createElement("article");
            bubble.className = `social-message${message.sender_id === window.FOURXProfile.profile?.id ? " own" : ""}`;
            const content = document.createElement("p");
            content.textContent = message.content;
            const meta = document.createElement("small");
            const time = message.created_at ? new Date(message.created_at).toLocaleTimeString([], {
                hour: "2-digit", minute: "2-digit",
            }) : "";
            meta.textContent = `${message.sender_name} · ${time}${message.sender_id === window.FOURXProfile.profile?.id ? ` · ${message.status}` : ""}`;
            bubble.append(content, meta);
            messages.append(bubble);
        });
        messages.scrollTop = messages.scrollHeight;
    }

    async sendMessage() {
        const input = document.getElementById("social-message-input");
        const content = input?.value.trim();
        if (!content || !this.conversationId) return;
        try {
            const message = await this.request(
                `/api/social/conversations/${encodeURIComponent(this.conversationId)}/messages`,
                { method: "POST", body: JSON.stringify({ content }) }
            );
            input.value = "";
            await this.loadMessages();
            await this.refreshDashboard();
            return message;
        } catch (error) {
            this.app.showToast(error.message, true);
        }
    }

    connect() {
        window.FOURXProfile.ready.then(() => {
            if (!window.FOURXProfile.token) return;
            const socket = new WebSocket(`${window.CONFIG.getWsUrl()}/social`);
            this.socket = socket;
            socket.onopen = () => {
                if (this.socket !== socket) return;
                socket.send(JSON.stringify({ type: "AUTH", token: window.FOURXProfile.token }));
                clearInterval(this.pingInterval);
                this.pingInterval = setInterval(() => this.sendSocket({ type: "PING" }), 20000);
            };
            socket.onmessage = (event) => {
                if (this.socket !== socket) return;
                let data;
                try {
                    data = JSON.parse(event.data);
                } catch (error) {
                    console.error("Could not parse FOURX social event.", error);
                    return;
                }
                this.handleSocketEvent(data);
            };
            socket.onclose = () => {
                if (this.socket !== socket) return;
                clearInterval(this.pingInterval);
                this.socket = null;
                clearTimeout(this.reconnectTimeout);
                this.reconnectTimeout = setTimeout(() => this.connect(), 3000);
            };
            socket.onerror = () => socket.close();
        }).catch((error) => {
            console.error("FOURX social profile could not initialize.", error);
        });
    }

    sendSocket(event) {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(event));
        }
    }

    handleSocketEvent(event) {
        if (event.type === "NOTIFICATION") {
            const notification = event.notification;
            if (notification && !this.seenNotifications.has(notification.id)) {
                this.seenNotifications.add(notification.id);
                const actor = notification.actor?.username || "A FOURX player";
                this.app.showToast(`${actor}: ${this.notificationText(notification)}`);
            }
            if (notification?.type === "invitation_accepted" && notification.payload?.room_code) {
                if (!this.app.roomCode && !this.app.classicChess.roomCode) {
                    this.app.joinSocialInvitation({
                        game_mode: notification.payload.game_mode,
                        ...notification.payload,
                    });
                }
            }
            this.refreshDashboard();
        } else if (event.type === "MESSAGE") {
            if (event.conversation_id === this.conversationId) {
                this.loadMessages().then(() => this.request(
                    `/api/social/conversations/${encodeURIComponent(this.conversationId)}/read`,
                    { method: "POST" }
                ));
            }
            this.refreshDashboard();
        } else if (event.type === "PRESENCE_UPDATE") {
            if (this.dashboard) {
                const friend = this.dashboard.friends.find((item) => item.id === event.player_id);
                if (friend) friend.status = event.status;
                const conversation = this.dashboard.conversations.find(
                    (item) => item.player.id === event.player_id
                );
                if (conversation) conversation.player.status = event.status;
                this.renderDashboard();
            }
        }
    }

    notificationText(notification) {
        return {
            friend_request: "sent you a friend request.",
            friend_accepted: "accepted your friend request.",
            new_message: notification.payload.preview || "sent you a message.",
            game_invitation: "invited you to a game.",
            invitation_accepted: "accepted your game invitation.",
            invitation_rejected: "declined your game invitation.",
        }[notification.type] || "sent you a FOURX update.";
    }
}

window.FOURXSocialController = FOURXSocialController;
