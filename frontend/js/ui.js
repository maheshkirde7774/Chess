/**
 * Neon Four Chess - UI Renderer & Interaction Controller
 * Handles 14x14 cross board rendering, neon piece SVGs, highlights, animations, and HUD modals.
 */

// Futuristic SVG Piece Templates (viewBox 0 0 100 100)
const PIECE_SVGS = {
    'K': `
        <svg viewBox="0 0 100 100" class="piece-svg">
            <!-- Cross -->
            <path d="M50 12 L50 26 M43 19 L57 19" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
            <!-- Crown Base & Arches -->
            <path d="M26 40 C34 32, 44 26, 50 26 C56 26, 66 32, 74 40 C68 56, 76 66, 75 74 L25 74 C24 66, 32 56, 26 40 Z" 
                  fill="currentColor" fill-opacity="0.18" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/>
            <!-- Decorative Jewels -->
            <circle cx="34" cy="46" r="3" fill="currentColor"/>
            <circle cx="50" cy="42" r="3.5" fill="currentColor"/>
            <circle cx="66" cy="46" r="3" fill="currentColor"/>
            <!-- Base Ring -->
            <rect x="22" y="74" width="56" height="8" rx="3" fill="currentColor" fill-opacity="0.3" stroke="currentColor" stroke-width="4"/>
            <path d="M18 84 L82 84" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
        </svg>
    `,
    'Q': `
        <svg viewBox="0 0 100 100" class="piece-svg">
            <!-- Queen Crown Points with Spheres -->
            <circle cx="20" cy="28" r="4" fill="currentColor"/>
            <circle cx="35" cy="22" r="4" fill="currentColor"/>
            <circle cx="50" cy="18" r="4.5" fill="currentColor"/>
            <circle cx="65" cy="22" r="4" fill="currentColor"/>
            <circle cx="80" cy="28" r="4" fill="currentColor"/>
            <!-- Coronet Body -->
            <path d="M20 32 L28 66 L72 66 L80 32 L65 48 L50 24 L35 48 Z" 
                  fill="currentColor" fill-opacity="0.2" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/>
            <!-- Base Ring -->
            <rect x="24" y="68" width="52" height="8" rx="3" fill="currentColor" fill-opacity="0.3" stroke="currentColor" stroke-width="4"/>
            <path d="M18 78 L82 78" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
        </svg>
    `,
    'R': `
        <svg viewBox="0 0 100 100" class="piece-svg">
            <!-- Battlement Crenellations -->
            <path d="M24 24 L34 24 L34 32 L44 32 L44 24 L56 24 L56 32 L66 32 L66 24 L76 24 L74 42 L26 42 Z" 
                  fill="currentColor" fill-opacity="0.22" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/>
            <!-- Tower Body -->
            <path d="M30 42 L34 72 L66 72 L70 42 Z" 
                  fill="currentColor" fill-opacity="0.15" stroke="currentColor" stroke-width="4.5"/>
            <!-- Slit window -->
            <line x1="50" y1="48" x2="50" y2="60" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
            <!-- Base Plinth -->
            <rect x="22" y="74" width="56" height="8" rx="3" fill="currentColor" fill-opacity="0.3" stroke="currentColor" stroke-width="4"/>
            <path d="M18 84 L82 84" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
        </svg>
    `,
    'B': `
        <svg viewBox="0 0 100 100" class="piece-svg">
            <!-- Top Finial -->
            <circle cx="50" cy="18" r="3.5" fill="currentColor"/>
            <!-- Mitre Hood -->
            <path d="M50 23 C36 23, 26 38, 28 54 C30 66, 42 70, 50 72 C58 70, 70 66, 72 54 C74 38, 64 23, 50 23 Z" 
                  fill="currentColor" fill-opacity="0.2" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/>
            <!-- Mitre Cut Slash -->
            <path d="M44 34 L56 46" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
            <!-- Base Ring -->
            <rect x="26" y="74" width="48" height="7" rx="3" fill="currentColor" fill-opacity="0.3" stroke="currentColor" stroke-width="4"/>
            <path d="M22 83 L78 83" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
        </svg>
    `,
    'N': `
        <svg viewBox="0 0 100 100" class="piece-svg">
            <!-- Cybernetic Knight Silhouette -->
            <path d="M32 80 L70 80 C68 70, 72 52, 60 40 C56 32, 58 20, 50 18 C46 22, 42 24, 38 24 C34 26, 26 32, 24 44 C24 50, 30 52, 34 50 C38 48, 42 56, 32 64 Z" 
                  fill="currentColor" fill-opacity="0.22" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/>
            <!-- Cyber Eye Glow -->
            <circle cx="38" cy="34" r="3" fill="currentColor"/>
            <!-- Mane Accent -->
            <path d="M52 28 L64 36 M54 42 L66 50" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
            <path d="M22 82 L78 82" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
        </svg>
    `,
    'P': `
        <svg viewBox="0 0 100 100" class="piece-svg">
            <!-- Pawn Head -->
            <circle cx="50" cy="28" r="14" fill="currentColor" fill-opacity="0.22" stroke="currentColor" stroke-width="4.5"/>
            <!-- Pawn Body -->
            <path d="M40 44 C34 56, 30 68, 28 74 L72 74 C70 68, 66 56, 60 44 Z" 
                  fill="currentColor" fill-opacity="0.18" stroke="currentColor" stroke-width="4.5" stroke-linejoin="round"/>
            <!-- Base Plinth -->
            <rect x="24" y="76" width="52" height="7" rx="3" fill="currentColor" fill-opacity="0.3" stroke="currentColor" stroke-width="4"/>
            <path d="M20 85 L80 85" stroke="currentColor" stroke-width="5" stroke-linecap="round"/>
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
        this.pendingPromotion = null; // {from: [r,c], to: [r,c]}

        this.boardContainer = document.getElementById("chessboard");
        this.turnBanner = document.getElementById("turn-banner");
        this.turnBadge = document.getElementById("turn-badge");

        this.initBoardDOM();
    }

    initBoardDOM() {
        this.boardContainer.innerHTML = "";
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

        // Render each square
        for (let r = 0; r < BOARD_SIZE; r++) {
            for (let c = 0; c < BOARD_SIZE; c++) {
                const sqEl = document.getElementById(`sq-${r}-${c}`);
                if (!sqEl || !isValidSquare(r, c)) continue;

                // Clear previous classes except base
                const isDark = (r + c) % 2 === 1;
                sqEl.className = `square active-square ${isDark ? 'dark-sq' : 'light-sq'}`;
                sqEl.innerHTML = "";

                const piece = this.engine.getPiece(r, c);
                if (piece) {
                    const pEl = document.createElement("div");
                    const pColor = piece.isDormant ? "dormant" : `player-${piece.player}`;
                    pEl.className = `chess-piece ${pColor}`;
                    pEl.innerHTML = PIECE_SVGS[piece.type] || "";
                    pEl.title = `${window.PLAYER_INFO[piece.player].name} ${piece.type}${piece.isDormant ? ' (Neutral)' : ''}`;
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

        // Update Turn Banner & Badges
        this.updateHUD();

        // Handle auto-rotation if enabled
        if (window.CONFIG.isAutoRotateEnabled()) {
            this.rotateToPlayer(this.engine.currentTurn);
        }
    }

    handleSquareClick(r, c) {
        if (this.engine.isGameOver) return;

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
                    this.executeMove({ from: [selR, selC], to: [r, c] });
                    this.selectedSquare = null;
                    this.currentLegalMoves = [];
                    return;
                }
            }
        }

        // Selecting a piece
        if (piece && piece.player === this.engine.currentTurn && !piece.isDormant) {
            // Check if online mode prevents moving this color
            if (window.app && window.app.isOnlineMode && window.app.myRole !== piece.player) {
                // Not authorized to move another player's army
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

        // Pass to callback (online sends to WS/API, local runs immediately)
        if (this.onMoveCallback) {
            this.onMoveCallback(move, isCapture);
        }
    }

    showPromotionModal() {
        const modal = document.getElementById("promotion-modal");
        const optionsContainer = document.getElementById("promotion-options");
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
                    this.pendingPromotion = null;
                    this.selectedSquare = null;
                    this.currentLegalMoves = [];
                    this.executeMove(finalMove);
                }
            });
            optionsContainer.appendChild(btn);
        });

        modal.classList.remove("hidden");
    }

    updateHUD() {
        const turn = this.engine.currentTurn;
        const info = window.PLAYER_INFO[turn];

        // Turn indicator badge
        if (this.turnBadge) {
            this.turnBadge.textContent = `${info.name}'s Turn`;
            this.turnBadge.style.borderColor = info.color;
            this.turnBadge.style.color = info.color;
            this.turnBadge.style.boxShadow = `0 0 12px ${info.color}`;
        }

        // Active Player Cards
        for (let p = 1; p <= 4; p++) {
            const card = document.getElementById(`player-card-${p}`);
            if (!card) continue;

            const isCurrent = (p === turn && !this.engine.isGameOver);
            const isEliminated = this.engine.eliminatedPlayers.includes(p);

            card.classList.toggle("active-turn-card", isCurrent);
            card.classList.toggle("eliminated-card", isEliminated);

            // Update captured pieces
            const capturedList = card.querySelector(".captured-pieces");
            if (capturedList) {
                const caps = this.engine.capturedPieces[p] || [];
                capturedList.innerHTML = caps.map(type => `<span class="cap-piece-icon">${type}</span>`).join("");
            }

            // In check badge
            const checkBadge = card.querySelector(".status-badge");
            if (checkBadge) {
                if (isEliminated) {
                    checkBadge.textContent = "ELIMINATED";
                    checkBadge.className = "status-badge eliminated";
                } else if (this.engine.isInCheck(p)) {
                    checkBadge.textContent = "CHECK!";
                    checkBadge.className = "status-badge in-check";
                } else if (isCurrent) {
                    checkBadge.textContent = "THINKING";
                    checkBadge.className = "status-badge thinking";
                } else {
                    checkBadge.textContent = "WAITING";
                    checkBadge.className = "status-badge waiting";
                }
            }
        }

        // Game Over Modal trigger
        if (this.engine.isGameOver) {
            this.showGameOverModal();
        }
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
            title.style.textShadow = `0 0 20px ${wInfo.color}`;
            details.innerHTML = `
                <div class="winner-trophy">🏆</div>
                <h3 style="color:${wInfo.color}; font-size:1.6rem; margin:10px 0;">${wInfo.name} Army Victorious!</h3>
                <p>The last standing commander in the neon arena.</p>
                <div class="gameover-stats">
                    <div><strong>${this.engine.turnNumber}</strong><span>Turns</span></div>
                    <div><strong>${this.engine.moveHistory.length}</strong><span>Total Moves</span></div>
                </div>
            `;
            window.soundSystem.playVictory();
        } else {
            title.textContent = "STALEMATE / DRAW";
            details.innerHTML = "<p>The battle ended in a stalemate. No victor stands alone.</p>";
        }

        modal.classList.remove("hidden");
    }

    rotateToPlayer(player) {
        // Cyan = 0deg, West/Magenta = 270deg, Lime = 180deg, Gold = 90deg
        const rotationMap = {
            1: 0,
            2: 270,
            3: 180,
            4: 90
        };
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
