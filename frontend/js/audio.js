/**
 * Quad Chess - Acoustic Tournament Audio Engine
 * High-fidelity procedural acoustic chess sounds synthesized via Web Audio API.
 * Provides realistic wood piece movement, capture impacts, subtle check tones, and tournament fanfares.
 */

class SoundSystem {
    constructor() {
        this.ctx = null;
        this.muted = !window.CONFIG.isAudioEnabled();
    }

    _initContext() {
        if (!this.ctx) {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (AudioContext) {
                this.ctx = new AudioContext();
            }
        }
        if (this.ctx && this.ctx.state === "suspended") {
            this.ctx.resume();
        }
    }

    toggleMute() {
        this.muted = !this.muted;
        window.CONFIG.setAudioEnabled(!this.muted);
        if (!this.muted) {
            this.playMove();
        }
        return this.muted;
    }

    /**
     * Authentic piece move: acoustic wooden tap/thud
     */
    playMove() {
        if (this.muted) return;
        this._initContext();
        if (!this.ctx) return;

        const now = this.ctx.currentTime;

        // 1. Low body resonance of wooden board
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(140, now);
        osc.frequency.exponentialRampToValueAtTime(50, now + 0.08);

        gain.gain.setValueAtTime(0.3, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);

        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now);
        osc.stop(now + 0.09);

        // 2. High crisp click of felt-padded wood
        const clickOsc = this.ctx.createOscillator();
        const clickGain = this.ctx.createGain();
        clickOsc.type = "triangle";
        clickOsc.frequency.setValueAtTime(480, now);
        clickOsc.frequency.exponentialRampToValueAtTime(180, now + 0.04);

        clickGain.gain.setValueAtTime(0.22, now);
        clickGain.gain.exponentialRampToValueAtTime(0.001, now + 0.045);

        clickOsc.connect(clickGain);
        clickGain.connect(this.ctx.destination);
        clickOsc.start(now);
        clickOsc.stop(now + 0.045);
    }

    /**
     * Authentic capture sound: heavier double impact with piece displacement
     */
    playCapture() {
        if (this.muted) return;
        this._initContext();
        if (!this.ctx) return;

        const now = this.ctx.currentTime;

        // Primary solid piece strike
        const osc1 = this.ctx.createOscillator();
        const gain1 = this.ctx.createGain();
        osc1.type = "triangle";
        osc1.frequency.setValueAtTime(260, now);
        osc1.frequency.exponentialRampToValueAtTime(70, now + 0.12);

        gain1.gain.setValueAtTime(0.4, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.13);

        osc1.connect(gain1);
        gain1.connect(this.ctx.destination);
        osc1.start(now);
        osc1.stop(now + 0.13);

        // Secondary tumble/knock
        setTimeout(() => {
            if (!this.ctx) return;
            const t = this.ctx.currentTime;
            const osc2 = this.ctx.createOscillator();
            const gain2 = this.ctx.createGain();
            osc2.type = "sine";
            osc2.frequency.setValueAtTime(180, t);
            osc2.frequency.exponentialRampToValueAtTime(45, t + 0.07);

            gain2.gain.setValueAtTime(0.2, t);
            gain2.gain.exponentialRampToValueAtTime(0.001, t + 0.08);

            osc2.connect(gain2);
            gain2.connect(this.ctx.destination);
            osc2.start(t);
            osc2.stop(t + 0.08);
        }, 35);
    }

    /**
     * Check warning: elegant dual harmonic bell chime
     */
    playCheck() {
        if (this.muted) return;
        this._initContext();
        if (!this.ctx) return;

        const now = this.ctx.currentTime;
        const freqs = [587.33, 880.00]; // D5, A5

        freqs.forEach((freq, idx) => {
            const start = now + (idx * 0.08);
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = "sine";
            osc.frequency.setValueAtTime(freq, start);

            gain.gain.setValueAtTime(0.18, start);
            gain.gain.exponentialRampToValueAtTime(0.001, start + 0.28);

            osc.connect(gain);
            gain.connect(this.ctx.destination);
            osc.start(start);
            osc.stop(start + 0.28);
        });
    }

    /**
     * Refined subtle button click
     */
    playClick() {
        if (this.muted) return;
        this._initContext();
        if (!this.ctx) return;

        const now = this.ctx.currentTime;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(600, now);
        osc.frequency.exponentialRampToValueAtTime(300, now + 0.025);

        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.03);

        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now);
        osc.stop(now + 0.03);
    }

    /**
     * Victory / Checkmate: Dignified tournament chord progression
     */
    playVictory() {
        if (this.muted) return;
        this._initContext();
        if (!this.ctx) return;

        const now = this.ctx.currentTime;
        // D-major triad ascending
        const notes = [
            { f: 293.66, t: 0.00 }, // D4
            { f: 369.99, t: 0.12 }, // F#4
            { f: 440.00, t: 0.24 }, // A4
            { f: 587.33, t: 0.38 }  // D5
        ];

        notes.forEach(note => {
            const start = now + note.t;
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = "triangle";
            osc.frequency.setValueAtTime(note.f, start);

            gain.gain.setValueAtTime(0.16, start);
            gain.gain.exponentialRampToValueAtTime(0.001, start + 0.65);

            osc.connect(gain);
            gain.connect(this.ctx.destination);
            osc.start(start);
            osc.stop(start + 0.65);
        });
    }

    /**
     * Clock low warning tick
     */
    playClockTick() {
        if (this.muted) return;
        this._initContext();
        if (!this.ctx) return;

        const now = this.ctx.currentTime;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(800, now);
        osc.frequency.exponentialRampToValueAtTime(400, now + 0.02);

        gain.gain.setValueAtTime(0.05, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.02);

        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(now);
        osc.stop(now + 0.02);
    }
}

// Global sound system instance
window.soundSystem = new SoundSystem();
