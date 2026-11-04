/**
 * FOURX Authentication & Account Controller
 * Manages user registration, email/username login, password reset,
 * session management, Google OAuth & Facebook OAuth handling, and profile synchronization.
 */

class FOURXAuth {
    constructor() {
        this.tokenKey = "fourx-device-profile-token";
        this.currentUser = null;
        this.isAuthenticated = false;
        this.isRegistered = false;
        this.googleClientId = null;
        this.gisInitialized = false;

        this.init();
    }

    async init() {
        this.bindEvents();
        this.checkUrlForOAuthCallback();
        await this.syncAuthStatus();
        await this.setupGoogleIdentityServices();
    }

    getServerUrl() {
        return window.CONFIG ? window.CONFIG.getServerUrl() : "";
    }

    getToken() {
        return localStorage.getItem(this.tokenKey);
    }

    setToken(token) {
        if (token) {
            localStorage.setItem(this.tokenKey, token);
            if (window.FOURXProfile) {
                window.FOURXProfile.token = token;
            }
        } else {
            localStorage.removeItem(this.tokenKey);
            if (window.FOURXProfile) {
                window.FOURXProfile.token = null;
            }
        }
    }

    authHeaders() {
        const token = this.getToken();
        return token ? { Authorization: `Bearer ${token}` } : {};
    }

    async request(endpoint, options = {}) {
        const url = `${this.getServerUrl()}${endpoint}`;
        const headers = {
            "Content-Type": "application/json",
            ...this.authHeaders(),
            ...(options.headers || {}),
        };
        const response = await fetch(url, { ...options, headers });
        let data = {};
        try {
            data = await response.json();
        } catch (e) {
            data = {};
        }
        if (!response.ok) {
            const errorMsg = data.detail || data.message || `Request failed with status ${response.status}`;
            const err = new Error(errorMsg);
            err.status = response.status;
            throw err;
        }
        return data;
    }

    async syncAuthStatus() {
        try {
            const token = this.getToken();
            if (!token) {
                this.updateUIForAnonymous();
                return;
            }
            const data = await this.request("/api/auth/status");
            if (data.authenticated) {
                this.currentUser = data.profile;
                this.isAuthenticated = true;
                this.isRegistered = !!data.is_registered;
                this.updateUIForUser(data.profile);
            } else {
                this.updateUIForAnonymous();
            }
        } catch (err) {
            console.warn("Failed to check auth status:", err);
            this.updateUIForAnonymous();
        }
    }

    updateUIForUser(profile) {
        // 1. Header auth button
        const navLabel = document.getElementById("nav-auth-label");
        const navBtn = document.getElementById("btn-nav-auth");
        if (navLabel) {
            navLabel.textContent = profile.username || "Account";
        }
        if (navBtn) {
            navBtn.classList.add("authenticated");
            navBtn.title = `Logged in as ${profile.username} (Click to view Profile)`;
        }

        // 2. Profile View Account Card
        const statusDot = document.getElementById("account-status-dot");
        const statusTitle = document.getElementById("account-status-title");
        const statusDesc = document.getElementById("account-status-desc");
        const loginBtn = document.getElementById("btn-profile-login-action");
        const logoutBtn = document.getElementById("btn-profile-logout");
        const authBadge = document.getElementById("profile-auth-badge");
        const emailDisplay = document.getElementById("profile-email-display");

        if (statusDot) {
            statusDot.className = "account-status-dot authenticated";
        }
        if (statusTitle) {
            statusTitle.textContent = `${profile.full_name || profile.username} (${profile.username})`;
        }
        if (statusDesc) {
            const provider = (profile.auth_provider || "FOURX").toUpperCase();
            statusDesc.textContent = `Verified ${provider} Account • Rating and statistics synced`;
        }
        if (emailDisplay && profile.email) {
            emailDisplay.textContent = profile.email;
            emailDisplay.classList.remove("hidden");
        }
        if (authBadge) {
            authBadge.textContent = (profile.auth_provider || "FOURX").toUpperCase();
            authBadge.classList.remove("hidden");
        }
        if (loginBtn) {
            loginBtn.classList.add("hidden");
        }
        if (logoutBtn) {
            logoutBtn.classList.remove("hidden");
        }

        window.dispatchEvent(new CustomEvent("fourx-auth-state-changed", { detail: { authenticated: true, profile } }));
    }

    updateUIForAnonymous() {
        this.currentUser = null;
        this.isAuthenticated = false;
        this.isRegistered = false;

        // 1. Header auth button
        const navLabel = document.getElementById("nav-auth-label");
        const navBtn = document.getElementById("btn-nav-auth");
        if (navLabel) {
            navLabel.textContent = "Sign In";
        }
        if (navBtn) {
            navBtn.classList.remove("authenticated");
            navBtn.title = "Sign In or Create Account";
        }

        // 2. Profile View Account Card
        const statusDot = document.getElementById("account-status-dot");
        const statusTitle = document.getElementById("account-status-title");
        const statusDesc = document.getElementById("account-status-desc");
        const loginBtn = document.getElementById("btn-profile-login-action");
        const logoutBtn = document.getElementById("btn-profile-logout");
        const authBadge = document.getElementById("profile-auth-badge");
        const emailDisplay = document.getElementById("profile-email-display");

        if (statusDot) {
            statusDot.className = "account-status-dot guest";
        }
        if (statusTitle) {
            statusTitle.textContent = "Guest Commander (Unlinked)";
        }
        if (statusDesc) {
            statusDesc.textContent = "Playing anonymously on this device. Sign in or register to preserve ratings and sync across devices.";
        }
        if (emailDisplay) {
            emailDisplay.classList.add("hidden");
        }
        if (authBadge) {
            authBadge.classList.add("hidden");
        }
        if (loginBtn) {
            loginBtn.classList.remove("hidden");
        }
        if (logoutBtn) {
            logoutBtn.classList.add("hidden");
        }

        window.dispatchEvent(new CustomEvent("fourx-auth-state-changed", { detail: { authenticated: false, profile: null } }));
    }

    bindEvents() {
        // Nav Auth button click
        document.getElementById("btn-nav-auth")?.addEventListener("click", () => {
            if (this.isAuthenticated && this.isRegistered) {
                window.app?.switchView("view-profile");
            } else {
                this.showAuthView("login");
            }
        });

        // Profile view action buttons
        document.getElementById("btn-profile-login-action")?.addEventListener("click", () => {
            this.showAuthView("login");
        });

        document.getElementById("btn-profile-logout")?.addEventListener("click", () => {
            this.logout();
        });

        // Return button from auth view
        document.getElementById("btn-auth-back-home")?.addEventListener("click", () => {
            window.app?.switchView("view-home");
        });

        // Auth Tab Switchers
        const tabLogin = document.getElementById("tab-auth-login");
        const tabRegister = document.getElementById("tab-auth-register");

        tabLogin?.addEventListener("click", () => this.switchTab("login"));
        tabRegister?.addEventListener("click", () => this.switchTab("register"));

        // Forgot password links
        document.getElementById("link-goto-forgot")?.addEventListener("click", () => {
            this.switchTab("forgot");
        });

        document.getElementById("link-back-to-login")?.addEventListener("click", () => {
            this.switchTab("login");
        });

        // Password visibility toggles
        document.getElementById("btn-toggle-login-pass")?.addEventListener("click", () => {
            this.togglePasswordVisibility("login-password");
        });
        document.getElementById("btn-toggle-reg-pass")?.addEventListener("click", () => {
            this.togglePasswordVisibility("register-password");
        });

        // Forms
        document.getElementById("form-auth-login")?.addEventListener("submit", (e) => this.handleLoginSubmit(e));
        document.getElementById("form-auth-register")?.addEventListener("submit", (e) => this.handleRegisterSubmit(e));
        document.getElementById("form-forgot-request")?.addEventListener("submit", (e) => this.handleForgotRequest(e));
        document.getElementById("form-forgot-confirm")?.addEventListener("submit", (e) => this.handleForgotConfirm(e));

        // Social Buttons
        document.getElementById("btn-google-login")?.addEventListener("click", () => this.handleGoogleLogin());
        document.getElementById("btn-facebook-login")?.addEventListener("click", () => this.handleFacebookLogin());
    }

    showAuthView(tab = "login") {
        this.switchTab(tab);
        window.app?.switchView("view-auth");
    }

    switchTab(tab) {
        const tabLogin = document.getElementById("tab-auth-login");
        const tabRegister = document.getElementById("tab-auth-register");
        const formLogin = document.getElementById("form-auth-login");
        const formRegister = document.getElementById("form-auth-register");
        const panelForgot = document.getElementById("panel-auth-forgot");
        const socialSection = document.getElementById("social-auth-section");
        const authDivider = document.getElementById("auth-divider");
        const authTabs = document.querySelector(".auth-tabs");
        const authTitle = document.getElementById("auth-title");
        const authSubtitle = document.getElementById("auth-subtitle");

        this.clearAlert();

        if (tab === "login") {
            tabLogin?.classList.add("active");
            tabRegister?.classList.remove("active");
            formLogin?.classList.remove("hidden");
            formRegister?.classList.add("hidden");
            panelForgot?.classList.add("hidden");
            socialSection?.classList.remove("hidden");
            authDivider?.classList.remove("hidden");
            authTabs?.classList.remove("hidden");
            if (authTitle) authTitle.textContent = "Welcome to FOURX";
            if (authSubtitle) authSubtitle.textContent = "Sign in to enter the battle arena.";
        } else if (tab === "register") {
            tabLogin?.classList.remove("active");
            tabRegister?.classList.add("active");
            formLogin?.classList.add("hidden");
            formRegister?.classList.remove("hidden");
            panelForgot?.classList.add("hidden");
            socialSection?.classList.remove("hidden");
            authDivider?.classList.remove("hidden");
            authTabs?.classList.remove("hidden");
            if (authTitle) authTitle.textContent = "Join FOURX Arena";
            if (authSubtitle) authSubtitle.textContent = "Create your grandmaster profile and sync your rating.";
        } else if (tab === "forgot") {
            tabLogin?.classList.remove("active");
            tabRegister?.classList.remove("active");
            formLogin?.classList.add("hidden");
            formRegister?.classList.add("hidden");
            panelForgot?.classList.remove("hidden");
            socialSection?.classList.add("hidden");
            authDivider?.classList.add("hidden");
            authTabs?.classList.add("hidden");
            if (authTitle) authTitle.textContent = "Reset Password";
            if (authSubtitle) authSubtitle.textContent = "Regain access to your FOURX commander account.";
            document.getElementById("forgot-step-1")?.classList.remove("hidden");
            document.getElementById("forgot-step-2")?.classList.add("hidden");
        }
    }

    togglePasswordVisibility(inputId) {
        const input = document.getElementById(inputId);
        if (!input) return;
        input.type = input.type === "password" ? "text" : "password";
    }

    showAlert(message, type = "error") {
        const alertEl = document.getElementById("auth-alert");
        if (!alertEl) return;
        alertEl.textContent = message;
        alertEl.className = `auth-alert ${type}`;
        alertEl.classList.remove("hidden");
    }

    clearAlert() {
        const alertEl = document.getElementById("auth-alert");
        if (alertEl) {
            alertEl.textContent = "";
            alertEl.classList.add("hidden");
        }
    }

    async handleLoginSubmit(event) {
        event.preventDefault();
        this.clearAlert();

        const identity = document.getElementById("login-identity")?.value.trim();
        const password = document.getElementById("login-password")?.value;

        if (!identity || !password) {
            this.showAlert("Please enter your email/username and password.");
            return;
        }

        const submitBtn = document.getElementById("btn-submit-login");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Signing In…";
        }

        try {
            const data = await this.request("/api/auth/login", {
                method: "POST",
                body: JSON.stringify({
                    email_or_username: identity,
                    password: password,
                }),
            });

            this.setToken(data.access_token);
            this.currentUser = data.profile;
            this.isAuthenticated = true;
            this.isRegistered = true;

            if (window.FOURXProfile) {
                window.FOURXProfile.profile = data.profile;
                window.FOURXProfile.renderProfile();
                window.FOURXProfile.loadMatches();
            }

            this.updateUIForUser(data.profile);
            window.app?.showToast(`Welcome back, ${data.profile.username}!`);
            window.app?.switchView("view-home");
        } catch (err) {
            this.showAlert(err.message || "Failed to sign in. Please verify your credentials.");
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "Sign In to FOURX";
            }
        }
    }

    async handleRegisterSubmit(event) {
        event.preventDefault();
        this.clearAlert();

        const fullName = document.getElementById("register-fullname")?.value.trim();
        const username = document.getElementById("register-username")?.value.trim();
        const email = document.getElementById("register-email")?.value.trim();
        const password = document.getElementById("register-password")?.value;
        const confirmPassword = document.getElementById("register-confirm-password")?.value;

        if (!fullName || !username || !email || !password || !confirmPassword) {
            this.showAlert("Please fill in all required fields.");
            return;
        }

        if (password !== confirmPassword) {
            this.showAlert("Passwords do not match.");
            return;
        }

        if (password.length < 8) {
            this.showAlert("Password must be at least 8 characters.");
            return;
        }

        const submitBtn = document.getElementById("btn-submit-register");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Creating Account…";
        }

        try {
            const data = await this.request("/api/auth/register", {
                method: "POST",
                body: JSON.stringify({
                    full_name: fullName,
                    username: username,
                    email: email,
                    password: password,
                    confirm_password: confirmPassword,
                }),
            });

            this.setToken(data.access_token);
            this.currentUser = data.profile;
            this.isAuthenticated = true;
            this.isRegistered = true;

            if (window.FOURXProfile) {
                window.FOURXProfile.profile = data.profile;
                window.FOURXProfile.renderProfile();
                window.FOURXProfile.loadMatches();
            }

            this.updateUIForUser(data.profile);
            window.app?.showToast("Account created successfully! Welcome to FOURX.");
            window.app?.switchView("view-home");
        } catch (err) {
            this.showAlert(err.message || "Failed to create account. Please check your details.");
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "Create Commander Account";
            }
        }
    }

    async handleForgotRequest(event) {
        event.preventDefault();
        this.clearAlert();

        const email = document.getElementById("forgot-email")?.value.trim();
        if (!email) {
            this.showAlert("Please enter your email address.");
            return;
        }

        const btn = document.getElementById("btn-request-reset");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Sending…";
        }

        try {
            const data = await this.request("/api/auth/forgot-password", {
                method: "POST",
                body: JSON.stringify({ email }),
            });

            // Show step 2
            document.getElementById("forgot-step-1")?.classList.add("hidden");
            const step2 = document.getElementById("forgot-step-2");
            if (step2) {
                step2.classList.remove("hidden");
                const tokenInput = document.getElementById("reset-token-input");
                if (tokenInput) {
                    tokenInput.value = "";
                    tokenInput.focus();
                }
            }
            this.showAlert("Password reset instructions have been sent to your email. Enter the verification code and your new password below.", "success");
        } catch (err) {
            this.showAlert(err.message || "Failed to request password reset.");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Request Reset Code";
            }
        }
    }

    async handleForgotConfirm(event) {
        event.preventDefault();
        this.clearAlert();

        const resetToken = document.getElementById("reset-token-input")?.value.trim();
        const newPassword = document.getElementById("reset-new-password")?.value;
        const confirmPassword = document.getElementById("reset-confirm-password")?.value;

        if (!resetToken || !newPassword || !confirmPassword) {
            this.showAlert("Please fill in all fields.");
            return;
        }

        if (newPassword !== confirmPassword) {
            this.showAlert("Passwords do not match.");
            return;
        }

        if (newPassword.length < 8) {
            this.showAlert("Password must be at least 8 characters.");
            return;
        }

        const btn = document.getElementById("btn-execute-reset");
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Resetting…";
        }

        try {
            await this.request("/api/auth/reset-password", {
                method: "POST",
                body: JSON.stringify({
                    reset_token: resetToken,
                    new_password: newPassword,
                    confirm_password: confirmPassword,
                }),
            });

            window.app?.showToast("Password reset successfully! Please sign in with your new password.");
            this.switchTab("login");
            this.showAlert("Password reset successfully! You can now sign in with your new password.", "success");
        } catch (err) {
            this.showAlert(err.message || "Failed to reset password. Please check your verification code.");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Save New Password & Sign In";
            }
        }
    }

    async logout() {
        if (window.google?.accounts?.id) {
            try {
                window.google.accounts.id.disableAutoSelect();
            } catch (e) {
                console.warn("GIS disableAutoSelect error:", e);
            }
        }

        try {
            await this.request("/api/auth/logout", { method: "POST" });
        } catch (e) {
            console.warn("Logout request error:", e);
        }

        // Invalidate active session and restore clean state
        this.setToken(null);
        this.updateUIForAnonymous();

        // Create new anonymous device profile so app remains completely functional
        if (window.FOURXProfile) {
            await window.FOURXProfile.initialize();
            window.FOURXProfile.renderProfile();
        }

        window.app?.showToast("You have been signed out safely.");
        this.showAuthView("login");
    }

    async setupGoogleIdentityServices() {
        try {
            const config = await this.request("/api/auth/google/config");
            if (!config || !config.configured || !config.client_id) {
                console.info("Google Identity Services: Client ID not configured on server.");
                return;
            }
            this.googleClientId = config.client_id;

            // Wait for Google Identity Services script to load
            let attempts = 0;
            const waitForGis = () => {
                if (window.google?.accounts?.id) {
                    this.initializeGisClient();
                } else if (attempts < 25) {
                    attempts++;
                    setTimeout(waitForGis, 200);
                }
            };
            waitForGis();
        } catch (err) {
            console.warn("Failed to load Google Auth configuration:", err);
        }
    }

    initializeGisClient() {
        if (!this.googleClientId || !window.google?.accounts?.id || this.gisInitialized) return;

        try {
            window.google.accounts.id.initialize({
                client_id: this.googleClientId,
                callback: (res) => this.handleGoogleCredentialResponse(res),
                auto_select: false,
                cancel_on_tap_outside: true,
                itp_support: true,
            });

            const gisContainer = document.getElementById("google-gis-btn-container");
            if (gisContainer) {
                window.google.accounts.id.renderButton(gisContainer, {
                    type: "standard",
                    theme: "filled_black",
                    size: "large",
                    text: "continue_with",
                    shape: "rectangular",
                    logo_alignment: "left",
                    width: 320,
                });
                // When GIS button renders, hide custom button fallback to avoid duplicates
                const fallbackBtn = document.getElementById("btn-google-login");
                if (fallbackBtn) {
                    fallbackBtn.style.display = "none";
                }
            }
            this.gisInitialized = true;
        } catch (e) {
            console.error("GIS initialization error:", e);
        }
    }

    async handleGoogleLogin() {
        this.clearAlert();
        const isCapacitorNative = !!(window.Capacitor?.isNativePlatform?.() || window.Capacitor?.getPlatform?.() === "android");

        if (!isCapacitorNative && this.gisInitialized && window.google?.accounts?.id) {
            // Web browser: Use Google Identity Services popup flow
            window.google.accounts.id.prompt((notification) => {
                if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
                    console.info("GIS prompt status:", notification.getNotDisplayedReason?.() || notification.getSkippedReason?.());
                }
            });
        } else {
            // Android WebView / fallback: Google disallows embedded webviews, so launch system browser OAuth flow
            try {
                const data = await this.request("/api/auth/google/url");
                if (data.configured && data.url) {
                    if (isCapacitorNative) {
                        window.open(data.url, "_system");
                    } else {
                        window.location.href = data.url;
                    }
                } else {
                    this.showAlert(
                        "Google Sign-In is configured on the backend and waiting for your GOOGLE_CLIENT_ID environment variable. Once set in your cloud deployment, one-click Google Login activates automatically.",
                        "info"
                    );
                }
            } catch (err) {
                this.showAlert("Could not initialize Google OAuth. Please check your network connection.");
            }
        }
    }

    async handleGoogleCredentialResponse(response) {
        if (!response || !response.credential) {
            this.showAlert("Google Sign-In did not provide a credential.");
            return;
        }

        this.clearAlert();
        const submitBtn = document.getElementById("btn-submit-login");
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Verifying with Google…";
        }

        try {
            const data = await this.request("/api/auth/google", {
                method: "POST",
                body: JSON.stringify({
                    credential: response.credential,
                }),
            });

            this.setToken(data.access_token);
            this.currentUser = data.profile;
            this.isAuthenticated = true;
            this.isRegistered = true;

            if (window.FOURXProfile) {
                window.FOURXProfile.profile = data.profile;
                window.FOURXProfile.renderProfile();
                window.FOURXProfile.loadMatches();
            }

            this.updateUIForUser(data.profile);
            window.app?.showToast(`Signed in with Google as ${data.profile.username}!`);
            window.app?.switchView("view-home");
        } catch (err) {
            this.showAlert(err.message || "Failed to sign in with Google.");
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = "Sign In to FOURX";
            }
        }
    }

    async handleFacebookLogin() {
        this.clearAlert();
        try {
            const data = await this.request("/api/auth/facebook/url");
            if (data.configured && data.url) {
                window.location.href = data.url;
            } else {
                this.showAlert(
                    "Facebook Login is prepared on the backend and awaiting your FACEBOOK_CLIENT_ID environment variable. Once configured, Facebook authentication will be immediately available.",
                    "info"
                );
            }
        } catch (err) {
            this.showAlert("Could not initialize Facebook OAuth. Please check your network connection.");
        }
    }

    checkUrlForOAuthCallback() {
        const processTokenOrError = (searchOrUrl) => {
            if (!searchOrUrl) return;
            let urlParams;
            try {
                if (searchOrUrl.includes("?")) {
                    urlParams = new URLSearchParams(searchOrUrl.substring(searchOrUrl.indexOf("?")));
                } else {
                    urlParams = new URLSearchParams(searchOrUrl);
                }
            } catch (e) {
                return;
            }
            const token = urlParams.get("auth_token");
            const error = urlParams.get("auth_error");

            if (token) {
                this.setToken(token);
                const cleanUrl = window.location.origin + window.location.pathname;
                window.history.replaceState({}, document.title, cleanUrl);
                window.app?.showToast("Successfully authenticated with Google!");
                this.syncAuthStatus();
            } else if (error) {
                const cleanUrl = window.location.origin + window.location.pathname;
                window.history.replaceState({}, document.title, cleanUrl);
                this.showAuthView("login");
                this.showAlert(decodeURIComponent(error));
            }
        };

        // Standard web browser check
        processTokenOrError(window.location.search);

        // Capacitor appUrlOpen listener for native Android deep links
        if (window.Capacitor?.Plugins?.App?.addListener) {
            try {
                window.Capacitor.Plugins.App.addListener("appUrlOpen", (data) => {
                    if (data?.url) {
                        processTokenOrError(data.url);
                    }
                });
            } catch (e) {
                console.warn("Capacitor App listener error:", e);
            }
        }
    }
}

// Instantiate on DOM load
document.addEventListener("DOMContentLoaded", () => {
    window.FOURXAuth = new FOURXAuth();
});
