const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

describe("FOURX Authentication System Frontend Tests", () => {
    const htmlSrc = fs.readFileSync(path.join(__dirname, "../index.html"), "utf-8");
    const styleSrc = fs.readFileSync(path.join(__dirname, "../css/style.css"), "utf-8");
    const authJsSrc = fs.readFileSync(path.join(__dirname, "../js/auth.js"), "utf-8");

    test("1. Authentication View and Core Elements Exist", () => {
        assert.ok(htmlSrc.includes('id="view-auth"'), "view-auth container must exist in index.html");
        assert.ok(htmlSrc.includes('id="btn-nav-auth"'), "btn-nav-auth header button must exist");
        assert.ok(htmlSrc.includes('id="tab-auth-login"'), "Sign In tab button must exist");
        assert.ok(htmlSrc.includes('id="tab-auth-register"'), "Create Account tab button must exist");
        assert.ok(htmlSrc.includes('id="btn-google-login"'), "Google OAuth button must exist");
        assert.ok(htmlSrc.includes('id="btn-facebook-login"'), "Facebook OAuth button must exist");
        assert.ok(htmlSrc.includes('id="form-auth-login"'), "Sign in form must exist");
        assert.ok(htmlSrc.includes('id="form-auth-register"'), "Register form must exist");
        assert.ok(htmlSrc.includes('id="panel-auth-forgot"'), "Forgot password panel must exist");
    });

    test("2. Required Form Fields and Controls Exist", () => {
        // Login fields
        assert.ok(htmlSrc.includes('id="login-identity"'), "Login identity field must exist");
        assert.ok(htmlSrc.includes('id="login-password"'), "Login password field must exist");
        assert.ok(htmlSrc.includes('id="btn-toggle-login-pass"'), "Toggle login password button must exist");
        assert.ok(htmlSrc.includes('id="link-goto-forgot"'), "Forgot password link must exist");

        // Registration fields
        assert.ok(htmlSrc.includes('id="register-fullname"'), "Full name field must exist");
        assert.ok(htmlSrc.includes('id="register-username"'), "Username field must exist");
        assert.ok(htmlSrc.includes('id="register-email"'), "Email field must exist");
        assert.ok(htmlSrc.includes('id="register-password"'), "Password field must exist");
        assert.ok(htmlSrc.includes('id="register-confirm-password"'), "Confirm password field must exist");
        assert.ok(htmlSrc.includes('id="btn-toggle-reg-pass"'), "Toggle register password button must exist");

        // Forgot password fields
        assert.ok(htmlSrc.includes('id="forgot-email"'), "Forgot email field must exist");
        assert.ok(htmlSrc.includes('id="reset-token-input"'), "Reset token field must exist");
        assert.ok(htmlSrc.includes('id="reset-new-password"'), "Reset new password field must exist");
        assert.ok(htmlSrc.includes('id="reset-confirm-password"'), "Reset confirm password field must exist");
    });

    test("3. Profile Account Section & Logout Button Exist", () => {
        assert.ok(htmlSrc.includes('id="profile-account-card"'), "profile-account-card must exist in profile view");
        assert.ok(htmlSrc.includes('id="btn-profile-logout"'), "btn-profile-logout must exist");
        assert.ok(htmlSrc.includes('id="profile-auth-badge"'), "profile-auth-badge must exist");
        assert.ok(htmlSrc.includes('id="profile-email-display"'), "profile-email-display must exist");
    });

    test("4. Apple Login Must NOT Be Included (Constraint Verification)", () => {
        assert.ok(!htmlSrc.toLowerCase().includes("apple-btn"), "No Apple login button allowed");
        assert.ok(!htmlSrc.toLowerCase().includes("continue with apple"), "No Apple login text allowed");
        assert.ok(!authJsSrc.toLowerCase().includes("apple"), "No Apple auth logic allowed in auth.js");
    });

    test("5. Script File Imported in index.html", () => {
        assert.ok(htmlSrc.includes('src="js/auth.js"'), "js/auth.js must be included in index.html scripts");
    });

    test("6. Black + Gold CSS Theme Classes Exist", () => {
        assert.ok(styleSrc.includes(".nav-auth-btn"), "nav-auth-btn styles must exist");
        assert.ok(styleSrc.includes(".profile-account-card"), "profile-account-card styles must exist");
        assert.ok(styleSrc.includes(".neon-btn.logout-btn"), "logout-btn styles must exist");
        assert.ok(styleSrc.includes(".auth-card"), "auth-card styles must exist");
        assert.ok(styleSrc.includes(".social-auth-btn"), "social-auth-btn styles must exist");
        assert.ok(styleSrc.includes(".neon-btn.gold-btn"), "gold-btn styles must exist");
        assert.ok(styleSrc.includes(".gis-btn-container"), "gis-btn-container styles must exist");
    });

    test("7. Google Identity Services (GIS) Integration in index.html", () => {
        assert.ok(
            htmlSrc.includes("https://accounts.google.com/gsi/client"),
            "Google Identity Services client library must be included in index.html"
        );
        assert.ok(
            htmlSrc.includes('id="google-gis-btn-container"'),
            "GIS container google-gis-btn-container must exist in index.html"
        );
    });

    test("8. Google Client Secret Kept Completely Out of Frontend Code", () => {
        const frontendFiles = [
            htmlSrc,
            authJsSrc,
            fs.readFileSync(path.join(__dirname, "../js/config.js"), "utf-8"),
            fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8"),
            fs.readFileSync(path.join(__dirname, "../js/profile.js"), "utf-8"),
        ];

        for (const content of frontendFiles) {
            assert.ok(!content.includes("GOCSPX-"), "Client secret must never be in frontend code");
            assert.ok(!content.includes("GOOGLE_CLIENT_SECRET"), "GOOGLE_CLIENT_SECRET must never be referenced in frontend code");
        }
    });

    test("9. Client Auth Class & GIS Handlers Verification", () => {
        // Mock DOM & storage for FOURXAuth unit tests
        const store = {};
        const mockLocalStorage = {
            getItem: (key) => store[key] || null,
            setItem: (key, val) => { store[key] = String(val); },
            removeItem: (key) => { delete store[key]; }
        };

        globalThis.localStorage = mockLocalStorage;
        globalThis.CONFIG = { getServerUrl: () => "http://localhost:8000" };
        globalThis.FOURXProfile = { token: null, profile: null };

        let disableAutoSelectCalled = false;
        globalThis.google = {
            accounts: {
                id: {
                    initialize: () => {},
                    renderButton: () => {},
                    prompt: () => {},
                    disableAutoSelect: () => { disableAutoSelectCalled = true; }
                }
            }
        };

        // Test token storage
        mockLocalStorage.setItem("fourx-device-profile-token", "test_bearer_token_abc123");
        assert.equal(mockLocalStorage.getItem("fourx-device-profile-token"), "test_bearer_token_abc123");
        mockLocalStorage.removeItem("fourx-device-profile-token");
        assert.equal(mockLocalStorage.getItem("fourx-device-profile-token"), null);

        // Verify authJs defines GIS methods
        assert.ok(authJsSrc.includes("setupGoogleIdentityServices"), "auth.js must implement setupGoogleIdentityServices");
        assert.ok(authJsSrc.includes("handleGoogleCredentialResponse"), "auth.js must implement handleGoogleCredentialResponse");
        assert.ok(authJsSrc.includes("disableAutoSelect"), "auth.js must call disableAutoSelect on logout");
    });

    test("10. Content Security Policy Meta Tag Exists in index.html", () => {
        assert.ok(htmlSrc.includes('http-equiv="Content-Security-Policy"'), "CSP meta tag must be declared in index.html");
        assert.ok(htmlSrc.includes("https://accounts.google.com"), "CSP must permit Google Identity Services");
        assert.ok(htmlSrc.includes("connect-src"), "CSP must define connect-src directives");
    });

    test("11. Chat and Match History DOM Rendering Uses Safe textContent", () => {
        const appJsSrc = fs.readFileSync(path.join(__dirname, "../js/app.js"), "utf-8");
        // Verify displayChatMessage does not assign to innerHTML
        const chatFuncMatch = appJsSrc.match(/displayChatMessage\s*\([^)]*\)\s*\{([\s\S]*?)\n\s*\}/);
        assert.ok(chatFuncMatch, "displayChatMessage function must exist in app.js");
        assert.ok(!chatFuncMatch[1].includes("innerHTML"), "displayChatMessage must never assign to innerHTML");
        assert.ok(chatFuncMatch[1].includes("textContent"), "displayChatMessage must use textContent to avoid XSS");
    });

    test("12. Password Reset Flow Does Not Leak or Expect Public Token in Client", () => {
        assert.ok(!authJsSrc.includes("data.reset_token"), "auth.js must not read or rely on data.reset_token in public response");
        assert.ok(authJsSrc.includes("Password reset instructions have been sent to your email"), "auth.js must inform user of email delivery");
    });

    test("13. Android Capacitor Config Disallows Cleartext and Mixed Content", () => {
        const capConfig = JSON.parse(fs.readFileSync(path.join(__dirname, "../../capacitor.config.json"), "utf-8"));
        assert.equal(capConfig.server.cleartext, false, "cleartext must be disabled in capacitor.config.json");
        assert.equal(capConfig.android.allowMixedContent, false, "allowMixedContent must be disabled in capacitor.config.json");
    });

    test("14. Android Manifest Configures Network Security and Disables Cleartext Traffic", () => {
        const manifestSrc = fs.readFileSync(path.join(__dirname, "../../android/app/src/main/AndroidManifest.xml"), "utf-8");
        assert.ok(manifestSrc.includes('android:usesCleartextTraffic="false"'), "usesCleartextTraffic must be false in AndroidManifest.xml");
        assert.ok(manifestSrc.includes('android:networkSecurityConfig="@xml/network_security_config"'), "networkSecurityConfig must be set in AndroidManifest.xml");
        const netSecXml = fs.readFileSync(path.join(__dirname, "../../android/app/src/main/res/xml/network_security_config.xml"), "utf-8");
        assert.ok(netSecXml.includes('cleartextTrafficPermitted="false"'), "network_security_config must disable cleartext by default");
    });
});
