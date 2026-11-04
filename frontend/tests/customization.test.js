const { test, describe } = require("node:test");
const assert = require("node:assert/strict");

describe("Frontend Customization Catalog Tests", () => {
    // Read and verify the customization definitions
    const fs = require("node:fs");
    const path = require("node:path");
    const customizationSrc = fs.readFileSync(path.join(__dirname, "../js/customization.js"), "utf-8");

    test("Theme definitions include 8 core themes + 2 premium singularity themes", () => {
        assert.ok(customizationSrc.includes('id: "classic_wood"'));
        assert.ok(customizationSrc.includes('id: "marble"'));
        assert.ok(customizationSrc.includes('id: "midnight"'));
        assert.ok(customizationSrc.includes('id: "ocean"'));
        assert.ok(customizationSrc.includes('id: "emerald"'));
        assert.ok(customizationSrc.includes('id: "royal_gold"'));
        assert.ok(customizationSrc.includes('id: "neon_cyber"'));
        assert.ok(customizationSrc.includes('id: "minimal_light"'));
        assert.ok(customizationSrc.includes('id: "singularity"'));
        assert.ok(customizationSrc.includes('id: "supernova"'));
    });

    test("Premium themes are marked with premium: true flag", () => {
        // Singularity and Supernova must have premium flag
        const singularityMatch = customizationSrc.match(/id:\s*"singularity"[^}]+premium:\s*true/);
        const supernovaMatch = customizationSrc.match(/id:\s*"supernova"[^}]+premium:\s*true/);
        assert.ok(singularityMatch, "Singularity must be designated as a premium theme");
        assert.ok(supernovaMatch, "Supernova must be designated as a premium theme");
    });

    test("Piece sets contain classic and vector variants", () => {
        assert.ok(customizationSrc.includes('id: "staunton"'));
        assert.ok(customizationSrc.includes('id: "modern"'));
        assert.ok(customizationSrc.includes('id: "futuristic"'));
        assert.ok(customizationSrc.includes('id: "obsidian"'));
    });

    test("Default audio volume and event toggles are configured", () => {
        assert.ok(customizationSrc.includes("volume: 0.65"));
        assert.ok(customizationSrc.includes("move: true"));
        assert.ok(customizationSrc.includes("capture: true"));
        assert.ok(customizationSrc.includes("check: true"));
        assert.ok(customizationSrc.includes("checkmate: true"));
    });
});

