const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

describe("Frontend SPA Navigation & Architecture Tests", () => {
    const htmlSrc = fs.readFileSync(path.join(__dirname, "../index.html"), "utf-8");
    const themeSrc = fs.readFileSync(path.join(__dirname, "../css/neon-theme.css"), "utf-8");
    const styleSrc = fs.readFileSync(path.join(__dirname, "../css/style.css"), "utf-8");

    test("All primary SPA views exist in index.html", () => {
        const requiredViews = [
            "view-home",
            "view-game",
            "view-profile",
            "view-customization",
            "view-membership",
            "view-live-games",
            "view-puzzles",
            "view-friends"
        ];
        for (const viewId of requiredViews) {
            assert.ok(htmlSrc.includes(`id="${viewId}"`), `View #${viewId} must be defined in index.html`);
        }
    });

    test("Home view is marked as default active-view", () => {
        assert.ok(
            htmlSrc.includes('id="view-home" class="app-view active-view"'),
            "view-home must have active-view class on initial load"
        );
    });

    test("7 Core Main Menu cards exist on Home screen", () => {
        const menuItems = [
            "menu-item-play-4p",
            "menu-item-classic-1v1",
            "menu-item-live-games",
            "menu-item-friends",
            "menu-item-ai",
            "menu-item-puzzles",
            "menu-item-profile"
        ];
        for (const id of menuItems) {
            assert.ok(htmlSrc.includes(`id="${id}"`), `Menu item button #${id} must exist`);
        }
    });

    test("Classic Chess 1v1 modal and boards are present", () => {
        assert.ok(htmlSrc.includes('id="classic-menu-modal"'), "classic-menu-modal must exist");
        assert.ok(htmlSrc.includes('id="classic-board"'), "classic-board container must exist");
        assert.ok(htmlSrc.includes('id="classic-result"'), "classic-result overlay must exist");
    });

    test("Top navigation controls are present", () => {
        assert.ok(htmlSrc.includes('id="btn-back-home"'), "Back button must exist");
        assert.ok(htmlSrc.includes('id="btn-membership-header"'), "Premium VIP Crown button must exist");
        assert.ok(htmlSrc.includes('id="btn-sound-toggle"'), "Sound toggle button must exist");
        assert.ok(htmlSrc.includes('id="btn-nav-rules"'), "Rules button must exist");
        assert.ok(htmlSrc.includes('id="btn-nav-settings"'), "Settings button must exist");
    });

    test("Home hero card has unified tournament presentation and no empty container", () => {
        assert.ok(htmlSrc.includes('class="home-hero-card"'), "home-hero-card must exist");
        assert.ok(htmlSrc.includes('class="pedestal-stage"'), "pedestal-stage must exist");
        assert.ok(htmlSrc.includes('class="hero-staunton-piece"'), "hero-staunton-piece SVG must exist");
        assert.ok(htmlSrc.includes('class="hero-titles"'), "hero-titles container must exist");
        assert.ok(htmlSrc.includes('class="hero-app-title"'), "hero-app-title must exist");
        assert.ok(htmlSrc.includes('class="hero-arena-tags"'), "hero-arena-tags chips must exist");
        assert.ok(!htmlSrc.includes('class="hero-showcase-panel"'), "Orphaned empty hero-showcase-panel must be removed");
    });

    test("Capacitor metadata is declared in capacitor.config.json", () => {
        const capConfig = JSON.parse(fs.readFileSync(path.join(__dirname, "../../capacitor.config.json"), "utf-8"));
        assert.equal(capConfig.appId, "com.neonchess.fourplayer");
        assert.equal(capConfig.appName, "FOURX");
        assert.equal(capConfig.webDir, "frontend");
        assert.equal(capConfig.server.cleartext, true);
    });

    test("Black + Gold primary theme tokens are declared in neon-theme.css", () => {
        assert.ok(themeSrc.includes("--bg-app: #080808;"), "--bg-app must be #080808 (Near Black)");
        assert.ok(themeSrc.includes("--bg-surface: #101010;"), "--bg-surface must be #101010 (Deep Black)");
        assert.ok(themeSrc.includes("--color-gold: #D4AF37;"), "--color-gold must be #D4AF37 (Primary Gold)");
        assert.ok(themeSrc.includes("--color-gold-light: #E8C96A;"), "--color-gold-light must be #E8C96A (Light Gold)");
        assert.ok(themeSrc.includes("--font-heading: 'Space Grotesk'"), "Heading font must be Space Grotesk");
        assert.ok(themeSrc.includes("--font-body: 'Inter'"), "Body font must be Inter");
    });

    test("Google Fonts link in index.html imports Inter and Space Grotesk", () => {
        assert.ok(htmlSrc.includes("family=Inter:wght@400;500;600;700"), "Inter weights must be imported");
        assert.ok(htmlSrc.includes("family=Space+Grotesk:wght@500;600;700"), "Space Grotesk weights must be imported");
    });

    test("Header action buttons use SVG icons without raw emoji characters", () => {
        const btnCrown = htmlSrc.match(/<button id="btn-membership-header"[^>]*>([\s\S]*?)<\/button>/)?.[1];
        const btnSound = htmlSrc.match(/<button id="btn-sound-toggle"[^>]*>([\s\S]*?)<\/button>/)?.[1];
        const btnRules = htmlSrc.match(/<button id="btn-nav-rules"[^>]*>([\s\S]*?)<\/button>/)?.[1];
        const btnSettings = htmlSrc.match(/<button id="btn-nav-settings"[^>]*>([\s\S]*?)<\/button>/)?.[1];

        assert.ok(btnCrown?.includes("<svg"), "VIP Crown button must use SVG");
        assert.ok(!btnCrown?.includes("👑"), "VIP Crown button must not have raw emoji");
        assert.ok(btnSound?.includes("<svg"), "Sound button must use SVG");
        assert.ok(!btnSound?.includes("🔊"), "Sound button must not have raw emoji");
        assert.ok(btnRules?.includes("<svg"), "Rules button must use SVG");
        assert.ok(btnSettings?.includes("<svg"), "Settings button must use SVG");
        assert.ok(!btnSettings?.includes("⚙"), "Settings button must not have raw emoji");
    });

    test("Home Screen displays official FOURX tagline", () => {
        assert.ok(htmlSrc.includes("FOUR PLAYERS. ONE BATTLE."), "Home hero title must display official tagline");
    });
});
