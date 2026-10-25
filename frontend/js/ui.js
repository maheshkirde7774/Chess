/**
 * Quad Chess / Four Player Grandmaster - UI Renderer & Interaction Controller
 * Renders realistic Staunton pieces, tournament cross board, coordinates,
 * smooth translation animations, digital chess clocks, and move history notation.
 */

// Classic Staunton-Inspired Vector Pieces with 3D Depth & Player Accent Gemstones
const PIECE_SVGS = {
    'K': `
        <svg viewBox="0 0 100 100" class="piece-svg piece-king" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="kingGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
                    <stop offset="50%" stop-color="#cbd5e1" stop-opacity="0.9"/>
                    <stop offset="100%" stop-color="#94a3b8" stop-opacity="0.85"/>
                </linearGradient>
                <filter id="pieceShadow" x="-15%" y="-15%" width="130%" height="130%">
                    <feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="#000000" flood-opacity="0.55"/>
                </filter>
            </defs>
            <g filter="url(#pieceShadow)">
                <!-- Cross Finial -->
                <path d="M50 11 L50 24 M43.5 17.5 L56.5 17.5" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
                <!-- Central Crown Peak -->
                <circle cx="50" cy="25" r="3.5" fill="currentColor"/>
                <!-- Imperial Diadem & Arches -->
                <path d="M26 38 C32 30, 42 27, 50 27 C58 27, 68 30, 74 38 C72 52, 75 64, 73 72 L27 72 C25 64, 28 52, 26 38 Z" 
                      fill="url(#kingGrad)" stroke="#1e293b" stroke-width="2.5" stroke-linejoin="round"/>
                <!-- Player Signature Accent Gem -->
                <polygon points="50,33 55,42 50,51 45,42" fill="currentColor" stroke="#0f172a" stroke-width="1.2"/>
                <circle cx="50" cy="42" r="2.2" fill="#ffffff" fill-opacity="0.9"/>
                <!-- Diadem Side Filigree -->
                <path d="M34 44 C38 41, 44 41, 46 45" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
                <path d="M66 44 C62 41, 56 41, 54 45" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/>
                <!-- Collar Ring -->
                <rect x="24" y="72" width="52" height="7" rx="3" fill="#334155" stroke="#1e293b" stroke-width="2"/>
                <rect x="28" y="73.5" width="44" height="4" rx="2" fill="currentColor" fill-opacity="0.45"/>
                <!-- Weighted Base Plinth -->
                <path d="M20 79 L80 79 C82 85, 78 88, 76 90 L24 90 C22 88, 18 85, 20 79 Z" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
            </g>
        </svg>
    `,
    'Q': `
        <svg viewBox="0 0 100 100" class="piece-svg piece-queen" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="queenGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
                    <stop offset="50%" stop-color="#cbd5e1" stop-opacity="0.9"/>
                    <stop offset="100%" stop-color="#94a3b8" stop-opacity="0.85"/>
                </linearGradient>
            </defs>
            <g filter="url(#pieceShadow)">
                <!-- Five Coronet Pearls -->
                <circle cx="20" cy="25" r="3.2" fill="currentColor"/>
                <circle cx="35" cy="20" r="3.5" fill="currentColor"/>
                <circle cx="50" cy="17" r="4" fill="currentColor"/>
                <circle cx="65" cy="20" r="3.5" fill="currentColor"/>
                <circle cx="80" cy="25" r="3.2" fill="currentColor"/>
                <!-- Coronet Body -->
                <path d="M20 28 L27 64 L73 64 L80 28 L65 44 L50 22 L35 44 Z" 
                      fill="url(#queenGrad)" stroke="#1e293b" stroke-width="2.5" stroke-linejoin="round"/>
                <!-- Royal Waist Jewel -->
                <ellipse cx="50" cy="52" rx="5" ry="6" fill="currentColor" stroke="#0f172a" stroke-width="1.2"/>
                <circle cx="50" cy="51" r="2" fill="#ffffff" fill-opacity="0.9"/>
                <!-- Mid Waist Ring -->
                <rect x="25" y="65" width="50" height="7" rx="3" fill="#334155" stroke="#1e293b" stroke-width="2"/>
                <!-- Weighted Base Plinth -->
                <path d="M21 72 L79 72 C81 80, 78 86, 75 88 L25 88 C22 86, 19 80, 21 72 Z" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
            </g>
        </svg>
    `,
    'R': `
        <svg viewBox="0 0 100 100" class="piece-svg piece-rook" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="rookGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
                    <stop offset="50%" stop-color="#cbd5e1" stop-opacity="0.9"/>
                    <stop offset="100%" stop-color="#94a3b8" stop-opacity="0.85"/>
                </linearGradient>
            </defs>
            <g filter="url(#pieceShadow)">
                <!-- Crenellations (Castle Battlements) -->
                <path d="M25 22 L33 22 L33 30 L43 30 L43 22 L57 22 L57 30 L67 30 L67 22 L75 22 L73 38 L27 38 Z" 
                      fill="url(#rookGrad)" stroke="#1e293b" stroke-width="2.5" stroke-linejoin="round"/>
                <!-- Arrow Slit Insignia -->
                <rect x="47.5" y="44" width="5" height="15" rx="2" fill="currentColor" stroke="#0f172a" stroke-width="1"/>
                <!-- Tower Body -->
                <path d="M30 38 L34 71 L66 71 L70 38 Z" 
                      fill="url(#rookGrad)" stroke="#1e293b" stroke-width="2.5"/>
                <!-- Player Accent Collar -->
                <rect x="26" y="71" width="48" height="6" rx="2.5" fill="currentColor" stroke="#1e293b" stroke-width="1.8"/>
                <!-- Heavy Base -->
                <path d="M21 77 L79 77 C81 83, 78 88, 76 90 L24 90 C22 88, 19 83, 21 77 Z" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
            </g>
        </svg>
    `,
    'B': `
        <svg viewBox="0 0 100 100" class="piece-svg piece-bishop" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="bishopGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
                    <stop offset="50%" stop-color="#cbd5e1" stop-opacity="0.9"/>
                    <stop offset="100%" stop-color="#94a3b8" stop-opacity="0.85"/>
                </linearGradient>
            </defs>
            <g filter="url(#pieceShadow)">
                <!-- Spherical Finial -->
                <circle cx="50" cy="16" r="3.8" fill="currentColor"/>
                <!-- Mitre Body with Elegant Slash -->
                <path d="M50 20 C36 20, 26 34, 28 52 C30 63, 40 68, 50 69 C60 68, 70 63, 72 52 C74 34, 64 20, 50 20 Z" 
                      fill="url(#bishopGrad)" stroke="#1e293b" stroke-width="2.5" stroke-linejoin="round"/>
                <!-- Papal Slash -->
                <path d="M44 32 L58 46" stroke="#0f172a" stroke-width="3" stroke-linecap="round"/>
                <!-- Center Accent Cross/Dot -->
                <circle cx="50" cy="56" r="3.2" fill="currentColor" stroke="#0f172a" stroke-width="1"/>
                <!-- Waist Ring -->
                <rect x="27" y="70" width="46" height="6" rx="2.5" fill="#334155" stroke="#1e293b" stroke-width="1.8"/>
                <!-- Plinth -->
                <path d="M22 76 L78 76 C80 82, 77 87, 75 89 L25 89 C23 87, 20 82, 22 76 Z" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
            </g>
        </svg>
    `,
    'N': `
        <svg viewBox="0 0 100 100" class="piece-svg piece-knight" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="knightGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
                    <stop offset="50%" stop-color="#cbd5e1" stop-opacity="0.9"/>
                    <stop offset="100%" stop-color="#94a3b8" stop-opacity="0.85"/>
                </linearGradient>
            </defs>
            <g filter="url(#pieceShadow)">
                <!-- Sculpted Steed Silhouette -->
                <path d="M30 75 L71 75 C68 64, 74 46, 61 36 C57 30, 58 19, 51 16 C46 19, 43 21, 39 21 C35 23, 27 29, 25 41 C25 47, 30 49, 34 47 C39 45, 43 53, 31 60 Z" 
                      fill="url(#knightGrad)" stroke="#1e293b" stroke-width="2.5" stroke-linejoin="round"/>
                <!-- Alert Eye -->
                <ellipse cx="37" cy="31" rx="2.5" ry="3" fill="currentColor" stroke="#0f172a" stroke-width="1"/>
                <circle cx="37.5" cy="30.5" r="1" fill="#ffffff"/>
                <!-- Mane Ridges with Accent -->
                <path d="M51 24 C57 27, 61 32, 63 38" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round"/>
                <path d="M56 38 C61 41, 65 47, 67 54" stroke="currentColor" stroke-width="2.5" fill="none" stroke-linecap="round"/>
                <!-- Base Band -->
                <rect x="25" y="75" width="50" height="6" rx="2.5" fill="currentColor" stroke="#1e293b" stroke-width="1.8"/>
                <path d="M21 81 L79 81 C81 86, 78 90, 75 91 L25 91 C22 90, 19 86, 21 81 Z" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
            </g>
        </svg>
    `,
    'P': `
        <svg viewBox="0 0 100 100" class="piece-svg piece-pawn" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="pawnGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/>
                    <stop offset="50%" stop-color="#cbd5e1" stop-opacity="0.9"/>
                    <stop offset="100%" stop-color="#94a3b8" stop-opacity="0.85"/>
                </linearGradient>
            </defs>
            <g filter="url(#pieceShadow)">
                <!-- Pawn Spherical Head -->
                <circle cx="50" cy="27" r="13" fill="url(#pawnGrad)" stroke="#1e293b" stroke-width="2.5"/>
                <!-- Accent Dot on Head Crown -->
                <circle cx="50" cy="24" r="3" fill="currentColor" stroke="#0f172a" stroke-width="1"/>
                <!-- Collar Ring -->
                <rect x="36" y="41" width="28" height="5" rx="2.5" fill="#334155" stroke="#1e293b" stroke-width="1.8"/>
                <!-- Tapered Conical Body -->
                <path d="M41 46 C37 57, 33 66, 30 73 L70 73 C67 66, 63 57, 59 46 Z" 
                      fill="url(#pawnGrad)" stroke="#1e293b" stroke-width="2.5" stroke-linejoin="round"/>
                <!-- Base Ring with Accent -->
                <rect x="27" y="73" width="46" height="6" rx="2.5" fill="currentColor" stroke="#1e293b" stroke-width="1.8"/>
                <!-- Weighted Plinth -->
                <path d="M22 79 L78 79 C80 84, 77 88, 75 90 L25 90 C23 88, 20 84, 22 79 Z" fill="#1e293b" stroke="#0f172a" stroke-width="2"/>
            </g>
        </svg>
    `
};

class ChessUI {
    constructor(engine, onMoveCallback) {
        this.engine = engine;
        this.onMoveCallback = onMoveCallback;
        this.selectedSquare = null;
        this.currentLegalMoves = [];
        this.boardRotation = 0; // 0, 90, 180, 270 deg
        this.pendingPromotion = null;
        this.isAnimating = false;

        // Clocks in seconds (default 10 minutes per player = 600s)
        this.clocks = { 1: 600, 2: 600, 3: 600, 4: 600 };
        this.clockInterval = null;

        this.boardContainer = document.getElementById("chessboard");
        this.boardScaler = document.getElementById("board-scaler");
        this.boardArena = document.getElementById("board-arena");
        this.turnBadge = document.getElementById("turn-badge");

        this.initBoardDOM();
        this.startChessClocks();
        this.initResizeObserver();
    }

    initResizeObserver() {
        if (typeof ResizeObserver !== "undefined" && this.boardArena) {
            const ro = new ResizeObserver(() => {
                this.resizeBoard();
            });
            ro.observe(this.boardArena);
        } else {
            window.addEventListener("resize", () => this.resizeBoard());
        }
        // Initial sizing run
        setTimeout(() => this.resizeBoard(), 50);
    }

    resizeBoard() {
        if (!this.boardArena || !this.boardScaler) return;
        const rect = this.boardArena.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) return;
        // Keep a neat 4px margin so the board rim never touches borders
        const available = Math.floor(Math.min(rect.width, rect.height) - 4);
        if (available > 120) {
            this.boardScaler.style.width = `${available}px`;
            this.boardScaler.style.height = `${available}px`;
        }
    }

    initBoardDOM() {
        if (!this.boardContainer) return;
        this.boardContainer.innerHTML = "";

        const files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n'];

        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const sq = document.createElement("div");
                sq.dataset.row = r;
                sq.dataset.col = c;
                sq.id = `sq-${r}-${c}`;

                if (!isValidSquare(r, c)) {
                    sq.className = "square void-square";
                } else {
                    const isDark = (r + c) % 2 === 1;
                    sq.className = `square active-square ${isDark ? 'dark-sq' : 'light-sq'}`;
                    
                    // Coordinates notation on edges
                    if (c === 0 || (c === 3 && (r < 3 || r > 10))) {
                        const rankLabel = document.createElement("span");
                        rankLabel.className = "coord-label coord-rank";
                        rankLabel.textContent = 14 - r;
                        sq.appendChild(rankLabel);
                    }
                    if (r === 13 || (r === 10 && (c < 3 || c > 10))) {
                        const fileLabel = document.createElement("span");
                        fileLabel.className = "coord-label coord-file";
                        fileLabel.textContent = files[c];
                        sq.appendChild(fileLabel);
                    }

                    sq.addEventListener("click", () => this.handleSquareClick(r, c));
                }
                this.boardContainer.appendChild(sq);
            }
        }
    }

    render(gameState = null) {
        if (gameState) {
            this.engine.syncFromServerState(gameState);
        }

        // Render each active square
        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const sqEl = document.getElementById(`sq-${r}-${c}`);
                if (!sqEl || !isValidSquare(r, c)) continue;

                // Retain coordinate labels
                const labels = sqEl.querySelectorAll(".coord-label");
                const isDark = (r + c) % 2 === 1;
                sqEl.className = `square active-square ${isDark ? 'dark-sq' : 'light-sq'}`;
                sqEl.innerHTML = "";
                labels.forEach(l => sqEl.appendChild(l));

                const piece = this.engine.getPiece(r, c);
                if (piece) {
                    const pEl = document.createElement("div");
                    const pColor = piece.isDormant ? "dormant" : `player-${piece.player}`;
                    pEl.className = `chess-piece ${pColor}`;
                    pEl.dataset.player = piece.player;
                    pEl.dataset.type = piece.type;
                    pEl.innerHTML = PIECE_SVGS[piece.type] || "";
                    pEl.title = `${window.PLAYER_INFO[piece.player]?.name || 'Player'} ${piece.type}${piece.isDormant ? ' (Neutral)' : ''}`;
                    sqEl.appendChild(pEl);
                }

                // King in check highlight
                if (piece && piece.type === 'K' && this.engine.isInCheck(piece.player)) {
                    sqEl.classList.add("in-check-glow");
                }

                // Last move highlight
                if (this.engine.lastMove) {
                    const [fr, fc] = this.engine.lastMove.from;
                    const [tr, tc] = this.engine.lastMove.to;
                    if ((r === fr && c === fc) || (r === tr && c === tc)) {
                        sqEl.classList.add("last-move-highlight");
                    }
                }
            }
        }

        // Render Selection and Legal Move Indicators
        if (this.selectedSquare) {
            const [selR, selC] = this.selectedSquare;
            const selEl = document.getElementById(`sq-${selR}-${selC}`);
            if (selEl) selEl.classList.add("selected-square");

            for (const m of this.currentLegalMoves) {
                const [tr, tc] = m.to;
                const targetEl = document.getElementById(`sq-${tr}-${tc}`);
                if (targetEl) {
                    const targetPiece = this.engine.getPiece(tr, tc);
                    const indicator = document.createElement("div");
                    if (targetPiece) {
                        indicator.className = "capture-ring";
                    } else {
                        indicator.className = "legal-move-dot";
                    }
                    targetEl.appendChild(indicator);
                }
            }
        }

        // Update HUD & Clocks
        this.updateHUD();

        // Handle auto-rotation if enabled
        if (window.CONFIG.isAutoRotateEnabled()) {
            this.rotateToPlayer(this.engine.currentTurn);
        }
    }

    /**
     * Animate smooth piece glide before updating DOM
     */
    animateAndExecuteMove(move, isCapture) {
        const [fromR, fromC] = move.from;
        const [toR, toC] = move.to;

        const fromSq = document.getElementById(`sq-${fromR}-${fromC}`);
        const toSq = document.getElementById(`sq-${toR}-${toC}`);
        const pieceEl = fromSq ? fromSq.querySelector(".chess-piece") : null;

        if (!fromSq || !toSq || !pieceEl || this.isAnimating) {
            this.executeMove(move);
            return;
        }

        this.isAnimating = true;

        const fromRect = fromSq.getBoundingClientRect();
        const toRect = toSq.getBoundingClientRect();
        const dx = toRect.left - fromRect.left;
        const dy = toRect.top - fromRect.top;

        // Apply smooth transition
        pieceEl.style.transition = "transform 0.22s cubic-bezier(0.2, 0.8, 0.2, 1)";
        pieceEl.style.transform = `translate(${dx}px, ${dy}px)`;
        pieceEl.style.zIndex = "40";

        setTimeout(() => {
            this.isAnimating = false;
            this.executeMove(move);
        }, 220);
    }

    handleSquareClick(r, c) {
        if (this.engine.isGameOver || this.isAnimating) return;

        const piece = this.engine.getPiece(r, c);

        // If a square is already selected, check if this is a legal move destination
        if (this.selectedSquare) {
            const [selR, selC] = this.selectedSquare;

            // Clicking the same square deselects
            if (selR === r && selC === c) {
                this.selectedSquare = null;
                this.currentLegalMoves = [];
                this.render();
                return;
            }

            // Check if (r, c) is among current legal moves
            const matchedMoves = this.currentLegalMoves.filter(m => m.to[0] === r && m.to[1] === c);

            if (matchedMoves.length > 0) {
                // Check if promotion
                const hasPromotion = matchedMoves.some(m => m.promotion);
                if (hasPromotion) {
                    this.pendingPromotion = { from: [selR, selC], to: [r, c] };
                    this.showPromotionModal();
                    return;
                } else {
                    const chosenMove = { from: [selR, selC], to: [r, c] };
                    const isCapture = this.engine.getPiece(r, c) !== null;
                    this.selectedSquare = null;
                    this.currentLegalMoves = [];
                    this.animateAndExecuteMove(chosenMove, isCapture);
                    return;
                }
            }
        }

        // Selecting a piece
        if (piece && piece.player === this.engine.currentTurn && !piece.isDormant) {
            // Check if online mode prevents moving this color
            if (window.app && window.app.isOnlineMode && window.app.myRole !== piece.player) {
                return;
            }
            // Check if Play vs AI mode prevents moving AI bots
            if (window.app && window.app.gameMode === "ai" && piece.player !== 1) {
                return;
            }

            this.selectedSquare = [r, c];
            const allLegal = this.engine.getLegalMoves(this.engine.currentTurn);
            this.currentLegalMoves = allLegal.filter(m => m.from[0] === r && m.from[1] === c);
            window.soundSystem.playClick();
            this.render();
        } else {
            this.selectedSquare = null;
            this.currentLegalMoves = [];
            this.render();
        }
    }

    executeMove(move) {
        const targetPiece = this.engine.getPiece(move.to[0], move.to[1]);
        const isCapture = targetPiece !== null;

        if (this.onMoveCallback) {
            this.onMoveCallback(move, isCapture);
        }
    }

    showPromotionModal() {
        const modal = document.getElementById("promotion-modal");
        const optionsContainer = document.getElementById("promotion-options");
        if (!modal || !optionsContainer) return;

        optionsContainer.innerHTML = "";
        const player = this.engine.currentTurn;
        const colorClass = `player-${player}`;
        const pieces = ['Q', 'R', 'B', 'N'];
        const names = { 'Q': 'Queen', 'R': 'Rook', 'B': 'Bishop', 'N': 'Knight' };

        pieces.forEach(p => {
            const btn = document.createElement("button");
            btn.className = `promo-btn ${colorClass}`;
            btn.innerHTML = `
                <div class="promo-icon">${PIECE_SVGS[p]}</div>
                <span>${names[p]}</span>
            `;
            btn.addEventListener("click", () => {
                modal.classList.add("hidden");
                if (this.pendingPromotion) {
                    const finalMove = {
                        from: this.pendingPromotion.from,
                        to: this.pendingPromotion.to,
                        promotion: p
                    };
                    const isCapture = this.engine.getPiece(finalMove.to[0], finalMove.to[1]) !== null;
                    this.pendingPromotion = null;
                    this.selectedSquare = null;
                    this.currentLegalMoves = [];
                    this.animateAndExecuteMove(finalMove, isCapture);
                }
            });
            optionsContainer.appendChild(btn);
        });

        modal.classList.remove("hidden");
    }

    startChessClocks() {
        if (this.clockInterval) clearInterval(this.clockInterval);
        this.clockInterval = setInterval(() => {
            if (this.engine.isGameOver) return;
            const cur = this.engine.currentTurn;
            if (this.clocks[cur] > 0) {
                this.clocks[cur]--;
                if (this.clocks[cur] === 10) {
                    window.soundSystem.playClockTick();
                }
                this.updateClockDisplays();
            } else if (this.clocks[cur] === 0) {
                // Time flag: eliminate on time
                this.engine.eliminatePlayer(cur);
                this.render();
            }
        }, 1000);
    }

    formatTime(sec) {
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        return `${m}:${s < 10 ? '0' : ''}${s}`;
    }

    updateClockDisplays() {
        for (let p = 1; p <= 4; p++) {
            const clockEl = document.getElementById(`clock-p${p}`);
            if (clockEl) {
                clockEl.textContent = this.formatTime(this.clocks[p]);
                if (this.clocks[p] < 30) {
                    clockEl.classList.add("clock-low");
                } else {
                    clockEl.classList.remove("clock-low");
                }
            }
        }
    }

    updateHUD() {
        const turn = this.engine.currentTurn;
        const info = window.PLAYER_INFO[turn] || { name: `Player ${turn}`, color: '#fff' };

        // Turn indicator badge
        if (this.turnBadge) {
            this.turnBadge.textContent = `${info.name}'s Move`;
            this.turnBadge.style.borderColor = info.color;
            this.turnBadge.style.color = info.color;
        }

        // Active Player Cards & Panels
        for (let p = 1; p <= 4; p++) {
            const card = document.getElementById(`player-card-${p}`);
            if (!card) continue;

            const isCurrent = (p === turn && !this.engine.isGameOver);
            const isEliminated = this.engine.eliminatedPlayers.includes(p);

            card.classList.toggle("active-turn-card", isCurrent);
            card.classList.toggle("eliminated-card", isEliminated);

            // Captured pieces rack
            const capturedList = card.querySelector(".captured-pieces");
            if (capturedList) {
                const caps = this.engine.capturedPieces[p] || [];
                capturedList.innerHTML = caps.map(type => `<span class="cap-piece-icon">${type}</span>`).join("");
            }

            // Status badges
            const checkBadge = card.querySelector(".status-badge");
            if (checkBadge) {
                if (isEliminated) {
                    checkBadge.textContent = "DEFEATED";
                    checkBadge.className = "status-badge eliminated";
                } else if (this.engine.isInCheck(p)) {
                    checkBadge.textContent = "CHECK!";
                    checkBadge.className = "status-badge in-check";
                } else if (isCurrent) {
                    checkBadge.textContent = "ACTIVE";
                    checkBadge.className = "status-badge thinking";
                } else {
                    checkBadge.textContent = "WAITING";
                    checkBadge.className = "status-badge waiting";
                }
            }

            // Digital clock active turn state
            const clockEl = document.getElementById(`clock-p${p}`);
            if (clockEl) {
                clockEl.classList.toggle("active-clock", isCurrent);
            }
        }

        this.updateClockDisplays();
        this.updateMoveHistoryNotation();

        // Game Over trigger
        if (this.engine.isGameOver) {
            this.showGameOverModal();
        }
    }

    updateMoveHistoryNotation() {
        const container = document.getElementById("move-history-list");
        if (!container) return;

        container.innerHTML = "";
        const history = this.engine.moveHistory || [];
        
        // Group into tournament rounds
        const files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n'];

        history.forEach((m, idx) => {
            const item = document.createElement("div");
            item.className = "history-item";
            const [fr, fc] = m.from;
            const [tr, tc] = m.to;
            const pInfo = window.PLAYER_INFO[m.player] || { color: '#fff' };
            const promo = m.promotion ? `=${m.promotion}` : "";
            const isCap = m.captured ? "×" : "-";
            const notation = `${m.piece.type} ${files[fc]}${14-fr}${isCap}${files[tc]}${14-tr}${promo}`;

            item.innerHTML = `
                <span class="hist-num">${idx + 1}.</span>
                <span class="hist-dot" style="background:${pInfo.color}"></span>
                <span class="hist-move">${notation}</span>
            `;
            container.appendChild(item);
        });

        container.scrollTop = container.scrollHeight;
    }

    showGameOverModal() {
        const modal = document.getElementById("gameover-modal");
        if (!modal) return;

        const title = document.getElementById("gameover-title");
        const details = document.getElementById("gameover-details");
        const winner = this.engine.winner;

        if (winner) {
            const wInfo = window.PLAYER_INFO[winner];
            title.textContent = `VICTORY!`;
            title.style.color = wInfo.color;
            details.innerHTML = `
                <div class="winner-trophy">🏆</div>
                <h3 style="color:${wInfo.color}; font-size:1.5rem; margin:10px 0;">${wInfo.name} Army Victorious</h3>
                <p style="color:var(--color-text-secondary); margin-bottom:16px;">The last standing grandmaster in the quad arena.</p>
                <div class="gameover-stats">
                    <div class="stat-pill"><strong>${this.engine.turnNumber}</strong><span>Turns</span></div>
                    <div class="stat-pill"><strong>${this.engine.moveHistory.length}</strong><span>Total Moves</span></div>
                    <div class="stat-pill"><strong style="color:#10b981">+24</strong><span>Rating Delta</span></div>
                </div>
            `;
            window.soundSystem.playVictory();
        } else {
            title.textContent = "DRAW / STALEMATE";
            details.innerHTML = "<p>The tournament match concluded without a sole victor standing.</p>";
        }

        modal.classList.remove("hidden");
    }

    rotateToPlayer(player) {
        const rotationMap = { 1: 0, 2: 270, 3: 180, 4: 90 };
        const deg = rotationMap[player] || 0;
        this.boardContainer.style.transform = `rotate(${deg}deg)`;
    }

    manualRotate() {
        this.boardRotation = (this.boardRotation + 90) % 360;
        this.boardContainer.style.transform = `rotate(${this.boardRotation}deg)`;
        window.soundSystem.playClick();
    }
}

window.ChessUI = ChessUI;
