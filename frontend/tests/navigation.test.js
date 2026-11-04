const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

describe("Frontend SPA Navigation & Architecture Tests", () => {
    const htmlSrc = fs.readFileSync(path.join(__dirname, "../index.html"), "utf-8");

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
});
