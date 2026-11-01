class DailyPuzzleUI {
    constructor(app) {
        this.app = app;
        this.puzzle = null;
        this.mode = "daily";
        this.moves = [];
        this.selectedSquare = null;
        this.timezoneLocked = false;
        this.busy = false;
        this.archiveOffset = 0;
        this.archiveLimit = 20;
        this.ready = this.initialize();
        this.bindEvents();
    }

    async initialize() {
        await window.FOURXProfile.ready;
        const timezoneInput = document.getElementById("puzzle-timezone");
        const profile = window.FOURXProfile.profile;
        if (timezoneInput) {
            timezoneInput.value = profile?.timezone
                || Intl.DateTimeFormat().resolvedOptions().timeZone
                || "UTC";
        }
        await this.loadDaily();
        await this.loadArchive(true);
    }

    bindEvents() {
        document.getElementById("daily-puzzle-board")?.addEventListener("click", event => {
            const square = event.target.closest("[data-square]");
            if (square) this.selectSquare(square.dataset.square);
        });
        document.getElementById("daily-puzzle-hint")?.addEventListener("click", () => this.getHint());
        document.getElementById("daily-puzzle-reset")?.addEventListener("click", () => this.reset());
        document.getElementById("daily-puzzle-today")?.addEventListener("click", () => this.loadDaily());
        document.getElementById("puzzle-timezone-save")?.addEventListener("click", () => this.saveTimezone());
        document.getElementById("daily-archive-difficulty")?.addEventListener("change", () => {
            this.archiveOffset = 0;
            this.loadArchive(true);
        });
        document.getElementById("daily-archive-more")?.addEventListener("click", () => {
            this.archiveOffset += this.archiveLimit;
            this.loadArchive(false);
        });
    }

    onViewEntered() {
        this.loadDaily();
        this.loadArchive(true);
    }

    async loadDaily() {
        this.mode = "daily";
        this.moves = [];
        this.selectedSquare = null;
        try {
            await window.FOURXProfile.ready;
            const puzzle = await window.FOURXProfile.request("/api/puzzles/daily");
            this.setPuzzle(puzzle, "daily");
        } catch (error) {
            this.setStatus(`Daily puzzle unavailable: ${error.message}`, true);
        }
    }

    setPuzzle(puzzle, mode) {
        this.puzzle = puzzle;
        this.mode = mode;
        if (mode === "daily" && puzzle.progress) {
            this.timezoneLocked = puzzle.progress.total_attempted > 0;
        }
        if (mode === "practice") {
            this.puzzle.attempt = {
                moves: [],
                incorrect_attempts: 0,
                hint_count: 0,
                completed: false,
                first_attempt_correct: false,
                xp_awarded: 0,
            };
        }
        this.moves = mode === "daily" ? [...(puzzle.attempt?.moves || [])] : [];
        this.selectedSquare = null;
        const practice = mode === "practice";
        const dateLabel = practice ? puzzle.published_date : puzzle.challenge_date;
        const title = document.getElementById("daily-puzzle-heading");
        const difficulty = document.getElementById("daily-puzzle-difficulty");
        const objective = document.getElementById("daily-puzzle-objective");
        const backToday = document.getElementById("daily-puzzle-today");
        const source = document.getElementById("daily-puzzle-source");
        const explanation = document.getElementById("daily-puzzle-explanation");
        if (title) title.textContent = `${practice ? "Archive practice" : "Daily puzzle"} · ${dateLabel}`;
        if (difficulty) {
            difficulty.textContent = `${puzzle.difficulty} · ${puzzle.rating}`;
            difficulty.dataset.difficulty = puzzle.difficulty;
        }
        if (objective) objective.textContent = puzzle.objective;
        if (backToday) backToday.classList.toggle("hidden", !practice);
        if (source) source.href = puzzle.source_url;
        if (explanation) explanation.classList.toggle("hidden", true);
        this.updateStats(puzzle.progress);
        this.updateAttemptState(puzzle.attempt);
        this.renderBoard();
        if (puzzle.attempt?.completed && !practice) {
            this.showCompletion(
                puzzle.explanation || "Puzzle solved. Review the verified solution and source game.",
                puzzle.attempt.xp_awarded,
            );
        } else {
            this.setStatus(practice
                ? "Practice mode · no XP or streak rewards."
                : "Find the best move. The server validates every submitted move.");
        }
    }

    updateStats(progress) {
        if (!progress) return;
        const values = {
            "daily-streak-current": String(progress.current_streak),
            "daily-streak-best": String(progress.best_streak),
            "daily-completed-count": String(progress.total_completed),
            "daily-accuracy": `${progress.accuracy}%`,
            "daily-xp-total": String(progress.total_xp_earned),
        };
        Object.entries(values).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) element.textContent = value;
        });
    }

    updateAttemptState(attempt = {}) {
        const errors = document.getElementById("daily-puzzle-errors");
        const counter = document.getElementById("daily-puzzle-move-count");
        const explanation = document.getElementById("daily-puzzle-explanation");
        const hintButton = document.getElementById("daily-puzzle-hint");
        const resetButton = document.getElementById("daily-puzzle-reset");
        const timezone = document.getElementById("puzzle-timezone");
        const timezoneSave = document.getElementById("puzzle-timezone-save");
        const dailyComplete = this.mode === "daily" && Boolean(attempt.completed);
        if (errors) errors.textContent = String(attempt.incorrect_attempts || 0);
        if (counter) counter.textContent = String(Math.ceil(this.moves.length / 2));
        if (hintButton) hintButton.disabled = this.busy || dailyComplete;
        if (resetButton) resetButton.disabled = this.busy || dailyComplete;
        if (timezone) timezone.disabled = Boolean(
            this.timezoneLocked || attempt.incorrect_attempts || attempt.hint_count || this.moves.length || dailyComplete,
        );
        if (timezoneSave) timezoneSave.disabled = timezone?.disabled || false;
        if (explanation && !dailyComplete) explanation.classList.add("hidden");
    }

    boardState() {
        const rows = this.puzzle.fen.split(" ")[0].split("/").map(row => {
            const cells = [];
            for (const token of row) {
                if (/\d/.test(token)) {
                    for (let count = Number(token); count > 0; count -= 1) cells.push(null);
                } else {
                    cells.push(token);
                }
            }
            return cells;
        });
        for (const uci of this.moves) {
            const sourceFile = uci.charCodeAt(0) - 97;
            const sourceRank = Number(uci[1]);
            const targetFile = uci.charCodeAt(2) - 97;
            const targetRank = Number(uci[3]);
            const sourceRow = 8 - sourceRank;
            const targetRow = 8 - targetRank;
            const piece = rows[sourceRow][sourceFile];
            if (!piece) continue;
            if (piece.toLowerCase() === "p" && sourceFile !== targetFile && !rows[targetRow][targetFile]) {
                rows[sourceRow][targetFile] = null;
            }
            rows[targetRow][targetFile] = uci.length === 5
                ? (piece === piece.toUpperCase() ? uci[4].toUpperCase() : uci[4])
                : piece;
            rows[sourceRow][sourceFile] = null;
            if (piece.toLowerCase() === "k" && Math.abs(targetFile - sourceFile) === 2) {
                const rookSource = targetFile > sourceFile ? 7 : 0;
                const rookTarget = targetFile > sourceFile ? targetFile - 1 : targetFile + 1;
                rows[sourceRow][rookTarget] = rows[sourceRow][rookSource];
                rows[sourceRow][rookSource] = null;
            }
        }
        return rows;
    }

    currentTurn() {
        const initialTurn = this.puzzle.fen.split(" ")[1] === "b" ? "b" : "w";
        return this.moves.length % 2 ? (initialTurn === "w" ? "b" : "w") : initialTurn;
    }

    renderBoard() {
        const board = document.getElementById("daily-puzzle-board");
        if (!board || !this.puzzle) return;
        const squares = this.boardState();
        const symbols = {
            K: "♔", Q: "♕", R: "♖", B: "♗", N: "♘", P: "♙",
            k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟",
        };
        const turn = this.currentTurn();
        board.replaceChildren();
        board.classList.toggle("is-complete", this.mode === "daily" && Boolean(this.puzzle.attempt?.completed));
        squares.forEach((row, rowIndex) => row.forEach((piece, columnIndex) => {
            const rank = 8 - rowIndex;
            const file = String.fromCharCode(97 + columnIndex);
            const coordinate = `${file}${rank}`;
            const square = document.createElement("button");
            square.type = "button";
            square.dataset.square = coordinate;
            square.className = `daily-square ${(rowIndex + columnIndex) % 2 ? "dark" : "light"}`;
            if (this.selectedSquare === coordinate) square.classList.add("selected");
            square.setAttribute("role", "gridcell");
            const isPlayerPiece = piece && (piece === piece.toUpperCase() ? "w" : "b") === turn;
            square.disabled = this.busy
                || (this.mode === "daily" && Boolean(this.puzzle.attempt?.completed))
                || (this.mode === "practice" && this.practiceCompleted)
                || (!this.selectedSquare && !isPlayerPiece);
            square.setAttribute(
                "aria-label",
                `${piece ? `${piece === piece.toUpperCase() ? "white" : "black"} ${this.pieceName(piece)} ` : ""}${coordinate}`,
            );
            if (piece) {
                const glyph = document.createElement("span");
                glyph.className = `daily-piece ${piece === piece.toUpperCase() ? "white-piece" : "black-piece"}`;
                glyph.textContent = symbols[piece];
                square.append(glyph);
            }
            if (columnIndex === 0 || rank === 1) {
                const coordinateLabel = document.createElement("small");
                coordinateLabel.className = "daily-coordinate";
                coordinateLabel.textContent = columnIndex === 0 && rank === 1
                    ? `${rank}${file}`
                    : columnIndex === 0 ? String(rank) : file;
                square.append(coordinateLabel);
            }
            board.append(square);
        }));
        this.updateAttemptState(this.mode === "daily" ? this.puzzle.attempt : {});
    }

    pieceName(piece) {
        return ({ k: "king", q: "queen", r: "rook", b: "bishop", n: "knight", p: "pawn" })[piece.toLowerCase()];
    }

    async selectSquare(coordinate) {
        if (!this.puzzle || this.busy) return;
        const clicked = document.querySelector(`#daily-puzzle-board [data-square="${coordinate}"]`);
        const clickedPiece = clicked?.querySelector(".daily-piece");
        if (this.selectedSquare) {
            if (coordinate === this.selectedSquare) {
                this.selectedSquare = null;
                this.renderBoard();
                return;
            }
            if (clickedPiece && this.squareBelongsToTurn(coordinate)) {
                this.selectedSquare = coordinate;
                this.renderBoard();
                return;
            }
            const uci = `${this.selectedSquare}${coordinate}${this.isPromotionMove(this.selectedSquare, coordinate) ? "q" : ""}`;
            this.selectedSquare = null;
            await this.submitMove(uci);
            return;
        }
        if (clickedPiece && this.squareBelongsToTurn(coordinate)) {
            this.selectedSquare = coordinate;
            this.renderBoard();
        }
    }

    squareBelongsToTurn(coordinate) {
        const row = 8 - Number(coordinate[1]);
        const column = coordinate.charCodeAt(0) - 97;
        const piece = this.boardState()[row][column];
        return piece && (piece === piece.toUpperCase() ? "w" : "b") === this.currentTurn();
    }

    isPromotionMove(from, to) {
        const row = 8 - Number(from[1]);
        const column = from.charCodeAt(0) - 97;
        const piece = this.boardState()[row][column];
        return piece?.toLowerCase() === "p" && (to[1] === "1" || to[1] === "8");
    }

    async submitMove(uci) {
        if (!this.puzzle) return;
        this.busy = true;
        this.renderBoard();
        try {
            let result;
            if (this.mode === "daily") {
                result = await window.FOURXProfile.request("/api/puzzles/daily/move", {
                    method: "POST",
                    body: JSON.stringify({ puzzle_id: this.puzzle.puzzle_id, move: uci }),
                });
            } else {
                result = await window.FOURXProfile.request(
                    `/api/puzzles/archive/${encodeURIComponent(this.puzzle.puzzle_id)}/move`,
                    {
                        method: "POST",
                        body: JSON.stringify({ move: uci, moves: this.moves }),
                    },
                );
            }
            if (!result.correct) {
                this.puzzle.attempt = this.puzzle.attempt || {};
                this.puzzle.attempt.incorrect_attempts = result.incorrect_attempts;
                if (this.mode === "daily") this.timezoneLocked = true;
                this.setStatus(result.message || "Not the solution. Try another move.", true);
                return;
            }
            this.moves = result.moves;
            if (result.completed) {
                if (this.mode === "daily") {
                    this.timezoneLocked = true;
                    this.puzzle.attempt.completed = true;
                    this.puzzle.attempt.xp_awarded = result.xp_awarded;
                    this.puzzle.attempt.incorrect_attempts = result.incorrect_attempts || this.puzzle.attempt.incorrect_attempts || 0;
                    this.puzzle.explanation = result.explanation;
                    this.updateStats(result.progress);
                    this.showCompletion(
                        result.explanation,
                        result.xp_awarded,
                        result.first_attempt_correct,
                    );
                    await this.loadArchive(true);
                } else {
                    this.practiceCompleted = true;
                    this.showCompletion(result.explanation, 0, false, true);
                }
            } else {
                if (this.mode === "daily") this.timezoneLocked = true;
                this.setStatus("Correct. Your opponent’s forced reply is shown on the board.");
            }
        } catch (error) {
            this.setStatus(error.message, true);
        } finally {
            this.busy = false;
            this.renderBoard();
        }
    }

    async getHint() {
        if (!this.puzzle) return;
        try {
            let result;
            if (this.mode === "daily") {
                result = await window.FOURXProfile.request("/api/puzzles/daily/hint", {
                    method: "POST",
                    body: JSON.stringify({ puzzle_id: this.puzzle.puzzle_id }),
                });
                this.puzzle.attempt = this.puzzle.attempt || {};
                this.puzzle.attempt.hint_count = result.hint_count;
                this.timezoneLocked = true;
            } else {
                const params = new URLSearchParams({ hint_level: "1" });
                this.moves.forEach(move => params.append("moves", move));
                result = await window.FOURXProfile.request(
                    `/api/puzzles/archive/${encodeURIComponent(this.puzzle.puzzle_id)}/hint?${params}`,
                );
            }
            const hint = document.getElementById("daily-puzzle-hint-text");
            if (hint) hint.textContent = result.hint;
            this.setStatus("Hint revealed. Solve the position to continue your streak.");
        } catch (error) {
            this.setStatus(error.message, true);
        }
        this.updateAttemptState(this.puzzle.attempt);
    }

    async reset() {
        if (!this.puzzle) return;
        if (this.mode === "daily") {
            try {
                await window.FOURXProfile.request("/api/puzzles/daily/reset", {
                    method: "POST",
                    body: JSON.stringify({ puzzle_id: this.puzzle.puzzle_id }),
                });
            } catch (error) {
                this.setStatus(error.message, true);
                return;
            }
        }
        this.moves = [];
        this.practiceCompleted = false;
        this.selectedSquare = null;
        const hint = document.getElementById("daily-puzzle-hint-text");
        if (hint) hint.textContent = "";
        this.renderBoard();
        this.setStatus(this.mode === "daily"
            ? "Position reset. Incorrect moves and hint history remain saved."
            : "Practice position reset. No XP or streak rewards are available.");
    }

    async saveTimezone() {
        const input = document.getElementById("puzzle-timezone");
        if (!input) return;
        try {
            const profile = await window.FOURXProfile.request("/api/profile", {
                method: "PATCH",
                body: JSON.stringify({ timezone: input.value.trim() }),
            });
            window.FOURXProfile.profile = profile;
            input.value = profile.timezone || "UTC";
            await this.loadDaily();
            this.setStatus("Daily reset timezone saved.");
        } catch (error) {
            this.setStatus(error.message, true);
        }
    }

    showCompletion(explanation, xp, firstAttempt = false, practice = false) {
        const panel = document.getElementById("daily-puzzle-explanation");
        const text = document.getElementById("daily-puzzle-explanation-text");
        const earned = document.getElementById("daily-puzzle-xp-earned");
        if (panel) {
            panel.classList.remove("hidden");
            panel.classList.add("puzzle-complete-pop");
        }
        if (text) text.textContent = explanation || "Review the verified solution on the source game.";
        if (earned) {
            earned.textContent = practice
                ? "Practice complete · no reward"
                : `+${xp} XP${firstAttempt ? " · first-attempt bonus included" : ""}`;
        }
        document.getElementById("daily-puzzle-board")?.classList.add("is-complete");
        this.setStatus(practice ? "Practice puzzle solved." : `Daily puzzle solved · +${xp} XP`);
    }

    setStatus(message, isError = false) {
        const status = document.getElementById("daily-puzzle-status");
        if (!status) return;
        status.textContent = message;
        status.classList.toggle("error", isError);
    }

    async loadArchive(clear) {
        const list = document.getElementById("daily-puzzle-archive-list");
        if (!list) return;
        if (clear) {
            this.archiveOffset = 0;
            list.replaceChildren();
        }
        try {
            const difficulty = document.getElementById("daily-archive-difficulty")?.value;
            const params = new URLSearchParams({
                offset: String(this.archiveOffset),
                limit: String(this.archiveLimit),
            });
            if (difficulty) params.set("difficulty", difficulty);
            const result = await window.FOURXProfile.request(`/api/puzzles/archive?${params}`);
            result.entries.forEach(entry => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = "daily-archive-entry";
                const title = document.createElement("strong");
                title.textContent = `${entry.published_date} · ${entry.difficulty}`;
                const description = document.createElement("span");
                description.textContent = `${entry.rating} rating · ${entry.objective}`;
                const outcome = document.createElement("small");
                outcome.textContent = entry.completed ? `Completed · +${entry.xp_awarded} XP` : "Practice · no reward";
                button.append(title, description, outcome);
                button.addEventListener("click", () => this.loadPractice(entry.puzzle_id));
                list.append(button);
            });
            const more = document.getElementById("daily-archive-more");
            if (more) more.classList.toggle("hidden", this.archiveOffset + result.entries.length >= result.total);
            if (clear && result.entries.length === 0) {
                const empty = document.createElement("p");
                empty.className = "profile-empty";
                empty.textContent = "The archive will fill as daily puzzles are published.";
                list.append(empty);
            }
        } catch (error) {
            const message = document.createElement("p");
            message.className = "profile-empty error";
            message.textContent = `Puzzle archive unavailable: ${error.message}`;
            list.append(message);
        }
    }

    async loadPractice(puzzleId) {
        try {
            const puzzle = await window.FOURXProfile.request(
                `/api/puzzles/archive/${encodeURIComponent(puzzleId)}`,
            );
            this.practiceCompleted = false;
            this.setPuzzle(puzzle, "practice");
        } catch (error) {
            this.setStatus(error.message, true);
        }
    }
}

window.DailyPuzzleUI = DailyPuzzleUI;
