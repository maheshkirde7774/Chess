<div align="center">

# ♟️ FOURX
### *FOUR PLAYERS. ONE BATTLE.*

[![Python](https://img.shields.io/badge/Python-3.14%2B-0ea5e9?style=for-the-badge&logo=python&logoColor=black)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-ec4899?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![WebSockets](https://img.shields.io/badge/WebSockets-Real--Time-10b981?style=for-the-badge&logo=websocket&logoColor=black)](https://websockets.readthedocs.io/)
[![Capacitor](https://img.shields.io/badge/Capacitor-Android%20Ready-f59e0b?style=for-the-badge&logo=capacitor&logoColor=black)](https://capacitorjs.com/)
[![Tests](https://img.shields.io/badge/Tests-28%20Passed-0ea5e9?style=for-the-badge&logo=pytest&logoColor=black)](backend/tests/)
[![License](https://img.shields.io/badge/License-MIT-ffffff?style=for-the-badge)](LICENSE)

<br/>

**FOURX** is a professional, tournament-grade four-player chess platform built on an authentic **14×14 cross-shaped arena**. Its premium charcoal-and-graphite identity uses a four-direction X mark with restrained cyan, purple, magenta, and gold accents. It includes online multiplayer, local pass-and-play, 2v2 alliance, AI opponents, classic 1v1 chess, puzzles, move clocks, and native Capacitor Android packaging.

[🎮 Features](#-key-features) • [📜 Rules of Engagement](#-rules-of-engagement) • [🗺️ Board Architecture](#️-board-architecture) • [⚔️ Commanders](#-the-four-commanders) • [🚀 Quickstart](#-quickstart-guide) • [📱 Android Build](#-android-build--deployment) • [📡 API & WebSockets](#-api--websocket-protocol)

---

</div>

## 🎮 Key Features

| Mode / System | Description |
|---|---|
| **⚔️ 14×14 Tournament Arena** | Authentic 160-square cross-shaped board with 3×3 corner voids, algebraic coordinate markings, and smooth piece translation animations. |
| **♟ Classic Chess 1v1** | Standard 8×8 chess in local pass-and-play, online room-code, and server-side FOURX AI matches with authoritative legal moves, clocks, draw controls, and saved games. |
| **🎨 Charcoal & Graphite Theme** | Minimalist dark aesthetic with subtle Cyan, Purple, Magenta, and Gold accents, realistic Staunton piece vectors, and dark slate squares. |
| **🤖 Tactical AI Bots** | Full single-player vs AI mode with 3 intelligent bots and selectable tactical tiers: Novice (800), Club (1400), and Master (2000). |
| **🤝 2v2 Team Alliance** | Team combat format: South (Cyan) & North (Lime) alliance battle West (Magenta) & East (Gold) with joint checkmate objectives. |
| **🌐 Online Multiplayer** | Private or public Classic 1v1 and four-player rooms, secure six-character invitation codes, ready/presence lobbies, host-controlled start, server-validated actions, and WebSocket reconnection. |
| **📱 Local Pass & Play** | Couch multiplayer on a single device with turn-privacy screens, auto-board rotation, and move undo. |
| **🧩 Tactical Daily Puzzles** | Multi-army chess puzzles with rating tracking, fork attacks, queen diversion sacrifices, and solution verifier. |
| **🏆 Global Leaderboards** | Competitive Elo rankings, win-rate metrics, leagues (Diamond & Master), and player profile statistics. |
| **🔊 Acoustic Chess Audio** | Authentic acoustic wood piece impacts, double capture knocks, harmonic check chimes, and tournament victory fanfares synthesized in Web Audio. |
| **💳 Grandmaster VIP & Themes** | Board finish customizer (Tournament Slate, Walnut Wood, Obsidian Carbon, Carrara Marble) and reserved clean AdMob banner container. |

---

## 🗺️ Board Architecture

The arena is played on a **14×14 grid** with four 3×3 corner voids removed, leaving **160 active battle squares**.

```
       Col:   0   1   2   3   4   5   6   7   8   9  10  11  12  13
Row  0       [░░░VOID░░░] [ R   N   B   Q   K   B   N   R ] [░░░VOID░░░]   <-- LIME (North)
Row  1       [░░░VOID░░░] [ P   P   P   P   P   P   P   P ] [░░░VOID░░░]
Row  2       [░░░VOID░░░] [ .   .   .   .   .   .   .   . ] [░░░VOID░░░]
Row  3        [ R   P   .   .   .   .   .   .   .   .   .   .   P   R ]
Row  4        [ N   P   .   .   .   .   .   .   .   .   .   .   P   N ]
Row  5        [ B   P   .   .   .   .   .   .   .   .   .   .   P   B ]
Row  6        [ Q   P   .   .   .   .   .   .   .   .   .   .   P   Q ]
Row  7        [ K   P   .   .   .   .   .   .   .   .   .   .   P   K ]
Row  8        [ B   P   .   .   .   .   .   .   .   .   .   .   P   B ]
Row  9        [ N   P   .   .   .   .   .   .   .   .   .   .   P   N ]
Row 10        [ R   P   .   .   .   .   .   .   .   .   .   .   P   R ]
Row 11       [░░░VOID░░░] [ .   .   .   .   .   .   .   . ] [░░░VOID░░░]
Row 12       [░░░VOID░░░] [ P   P   P   P   P   P   P   P ] [░░░VOID░░░]
Row 13       [░░░VOID░░░] [ R   N   B   Q   K   B   N   R ] [░░░VOID░░░]   <-- CYAN (South)
                 ^                                             ^
            MAGENTA (West)                                 GOLD (East)
```

---

## ⚔️ The Four Commanders

Each army commands 16 cybernetic units (1 King, 1 Queen, 2 Rooks, 2 Bishops, 2 Knights, 8 Pawns):

```
┌──────────────┬──────────────────┬───────────┬──────────────┬────────────────────────┐
│ Commander    │ Flank            │ Color     │ Accent Code  │ Starting Back-Rank     │
├──────────────┼──────────────────┼───────────┼──────────────┼────────────────────────┤
│ Player 1     │ South (Bottom)   │ 🟦 Cyan   │ #00F3FF      │ Row 13, Cols 3..10     │
│ Player 2     │ West (Left)      │ 🟪 Magenta│ #FF007F      │ Col 0,  Rows 3..10     │
│ Player 3     │ North (Top)      │ 🟩 Lime   │ #39FF14      │ Row 0,  Cols 3..10     │
│ Player 4     │ East (Right)     │ 🟨 Gold   │ #FFD700      │ Col 13, Rows 3..10     │
└──────────────┴──────────────────┴───────────┴──────────────┴────────────────────────┘
```

---

## 📜 Rules of Engagement

1. **Clockwise Turn Order**: Combat proceeds cyclically: **Cyan (1) → Magenta (2) → Lime (3) → Gold (4)**.
2. **Dynamic Pawn Propulsion**:
   - Pawns advance towards the center of the board relative to their home rank.
   - Initial 2-square thrust is allowed on their first move.
   - Diagonal captures function forward-diagonally in their army's heading.
3. **8th-Rank Pawn Promotion**:
   - Reaching the **8th rank** relative to starting rank (or reaching an opposite back boundary) triggers instant promotion to **Queen, Rook, Bishop, or Knight**.
4. **Castling for All 4 Armies**:
   - Supported on both wings for every commander provided King and Rook have not moved and path squares are unobstructed and unattacked.
5. **Check & Pins**:
   - If an active enemy piece targets a King, that commander is placed in **Check**.
   - On their turn, the commander must resolve the threat. Moves that leave the King in check are illegal.
6. **Elimination & Dormant Neutral Obstacles**:
   - If a player is checkmated or resigns, their King is permanently removed.
   - Their remaining pieces become **dormant neutral obstacles**: they can no longer move or attack, but may be captured by remaining commanders.
   - Turn order permanently skips eliminated players.
7. **Last Commander Standing**: The last remaining commander with their King intact wins the arena!

---

## 🛠️ Technology Stack

```
Frontend:           Vanilla ES6+ JavaScript, Responsive CSS Grid, Semantic HTML5
Audio:              Web Audio API (Procedural sound synthesis)
Backend Engine:     Python 3.10+ (tested on Python 3.14)
API Framework:      FastAPI, Uvicorn (ASGI)
Multiplayer:        WebSockets (Async Connection Manager)
Database:           SQLAlchemy ORM + SQLite (Production-ready for PostgreSQL)
Mobile Wrapper:     Capacitor 6 (Android Studio native integration)
Testing:            pytest (Engine rules, API flows, WebSocket synchronization)
```

---

## 📁 Repository Structure

```
Chess/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI application, REST endpoints, WebSockets, static serving
│   │   ├── engine.py            # 14x14 cross board engine (rules, moves, checks, elimination)
│   │   ├── models.py            # Pydantic request/response schemas
│   │   ├── db.py                # SQLite database models (rooms, game history)
│   │   └── ws_manager.py        # WebSocket ConnectionManager with broadcast & reconnect
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_engine.py       # Engine tests (geometry, pieces, pawns, promotion, check, elimination)
│   │   ├── test_api.py          # REST API tests (create room, join, move authorization, resign)
│   │   └── test_websockets.py   # WebSocket tests (sync, ping/pong, move broadcasts)
│   ├── requirements.txt         # Python dependencies
│   └── run.py                   # Server startup runner script
├── frontend/
│   ├── index.html               # Semantic HTML5 app layout, HUD, board, modals
│   ├── css/
│   │   ├── neon-theme.css       # Color tokens, player themes, glow variables
│   │   └── style.css            # Responsive 14x14 grid, HUD cards, animations, media queries
│   ├── js/
│   │   ├── config.js            # Dynamic server URL detection & user preferences
│   │   ├── audio.js             # Synthesized Web Audio API sound generator
│   │   ├── chess-engine-client.js # Client-side engine mirror for snappy local play & highlights
│   │   ├── ui.js                # SVG vector pieces, 14x14 DOM rendering, HUD modals
│   │   ├── ws-client.js         # WebSocket client with heartbeat and auto-reconnect
│   │   └── app.js               # Main game coordinator (Local & Online modes)
│   └── assets/
│       ├── icon.png             # FOURX four-direction app icon (1:1)
│       └── splash.png           # FOURX mobile launch screen (9:16)
├── android/                     # Capacitor native Android project
│   └── app/src/main/
│       ├── AndroidManifest.xml  # Android permissions and cleartext traffic
│       └── res/                 # Generated mipmap icons & splash screens
├── scripts/
│   └── copy_assets.py           # Asset synchronizer script
├── capacitor.config.json        # Capacitor configuration
├── package.json                 # Node/Capacitor project metadata
├── .env.example                 # Environment variables template
└── README.md                    # Project documentation
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Python 3.10+** (tested on Python 3.14)
- **Node.js 18+** & **npm**

### 2. Windows PowerShell Setup

```powershell
# 1. Clone repository
git clone https://github.com/maheshkirde7774/Chess.git
cd Chess

# 2. (Optional) Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install backend dependencies
pip install -r backend/requirements.txt

# 4. Run automated test suite
pytest backend/tests/ -v

# 5. Start the server
python backend/run.py
```

### 3. Open in Browser
- **Live Playable Web App**: [http://localhost:8000](http://localhost:8000)
- **Interactive Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **LAN / Mobile URL**: `http://<YOUR_LOCAL_IP>:8000`

## Classic 1v1 Chess

Choose **Classic Chess (1v1)** on the home screen to select local pass-and-play or online play. Online games use a six-character room code; the host starts once both seats are occupied. Public rooms appear in the room browser, while private rooms are invitation-only. The available clocks are 1+0, 3+0, 5+0, 10+0, 15+10, and unlimited. The server validates moves and keeps each match, its move history, and remaining clock time in the separate `classic_rooms` SQLite table. Threefold repetition and the fifty-move rule are claimable draws; automatic terminal draws are handled by the chess rules engine.

Classic mode uses separate `/classic/rooms` REST endpoints and `/ws/classic/{room_code}` WebSockets. Choose **Play vs FOURX AI** for Beginner, Intermediate, Advanced, or Expert play, select White or Black, and use any supported Classic time control. The built-in AI runs server-side using bounded minimax with alpha-beta pruning, iterative deepening, material/positional evaluation, and difficulty-specific depth, node, and time limits. It uses the existing `python-chess` legal move generator and Classic game state, so no Stockfish executable or mobile binary is distributed. Search runs off the event loop, and cancellation is checked during search when a match is restarted or resigned.

Four-player rooms use `/rooms` and `/ws/{room_code}` and keep the original four-player engine. Four-player time-control selections are saved as room settings; authoritative four-player clocks and Four-Player AI are not implemented.

Both online modes provide a waiting lobby with room code copy/share, occupied and empty seats, presence/readiness, host start, and waiting-room leave. Share uses the native Web Share API when available and falls back to copying the room code. Player credentials are bearer secrets returned only to the matching player; they are excluded from room snapshots and broadcasts.

---

## 📱 Android Build & Deployment

The application includes an Android wrapper powered by **Capacitor 6**.

### Connecting a Physical Android Phone

A phone on your Wi-Fi cannot access `localhost`. To test on a real phone:
1. Ensure your phone and PC are connected to the same Wi-Fi.
2. Find your PC's LAN IP in PowerShell:
   ```powershell
   ipconfig
   # Look for IPv4 Address (e.g., 192.168.1.50)
   ```
3. Open the game on your phone:
   - Tap **⚙ Settings** in the top right.
   - Enter `http://192.168.1.50:8000` into **Backend Server URL**.
   - Tap **Test** → **Save Preferences**.

### Building the Debug APK

```powershell
# 1. Install Capacitor dependencies
npm install

# 2. Sync web build to Android native project
npx cap sync

# 3. Build Debug APK via Gradle
cd android
.\gradlew.bat assembleDebug

# Output APK located at:
# android/app/build/outputs/apk/debug/app-debug.apk
```

---

## 📡 API & WebSocket Protocol

### REST Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check & active room count |
| `POST` | `/rooms` | Create a room (assigns Player 1: Cyan) |
| `POST` | `/rooms/join` | Join room by code (assigns next open seat 2..4) |
| `GET` | `/rooms` | List public waiting rooms |
| `GET` | `/rooms/{code}` | Retrieve full serialized board state & active players |
| `POST` | `/rooms/{code}/start` | Start a full room as its host |
| `POST` | `/rooms/{code}/leave` | Leave a waiting room |
| `POST` | `/rooms/{code}/move` | Authoritative move submission |
| `POST` | `/rooms/{code}/resign` | Resign current player |
| `POST` | `/rooms/{code}/reset` | Rematch & reset board |
| `GET` | `/api/history` | Match log of completed games |
| `POST` | `/classic/rooms` | Create a local or online classic 1v1 match |
| `POST` | `/classic/rooms/join` | Join an available classic match as Black |
| `POST` | `/classic/rooms/{code}/start` | Start a full Classic room as its host |
| `POST` | `/classic/rooms/{code}/leave` | Leave a waiting Classic room |
| `POST` | `/classic/rooms/{code}/restart` | Restart an authorized local or AI Classic match |
| `POST` | `/classic/rooms/{code}/resign` | Resign an authorized active AI match |
| `GET` | `/classic/rooms/{code}` | Retrieve authorized classic state with `Authorization: Bearer <player_id>` |

### WebSocket Frame Specification (`/ws/{room_code}`)

```json
// Outgoing Move Frame (Client -> Server)
{
  "type": "MOVE",
  "from": [12, 6],
  "to": [10, 6],
  "promotion": "Q"
}

// Broadcast Move Event (Server -> Clients)
{
  "type": "MOVE_MADE",
  "room_code": "FOURX7",
  "player": 1,
  "move": { "from": [12, 6], "to": [10, 6], "promotion": "Q" },
  "game_state": { /* full 14x14 state, active players, turn */ },
  "is_game_over": false,
  "winner": null
}

// Tactical Chat Emote (Client -> Server)
{
  "type": "CHAT",
  "text": "Check!"
}
```

Both WebSocket endpoints authenticate with an initial `{"type":"AUTH","player_id":"…"}` frame; credentials are not placed in WebSocket URLs. Classic `MOVE` frames use algebraic squares (`e2` to `e4`) and optional promotion (`q`, `r`, `b`, or `n`); `RESIGN`, `OFFER_DRAW`, `ACCEPT_DRAW`, and `DECLINE_DRAW` are also supported. Both players receive sanitized state updates after accepted actions; player IDs are returned only to the matching player.

---

## 🔬 Testing & Quality Assurance

All current backend tests, including the original four-player tests and the classic chess suite, pass:

```powershell
pytest backend/tests/ -v
```

The backend suite includes Classic AI legality, difficulty-budget, side selection, timed moves, cancellation, and terminal-position tests. Run all tests, including the original four-player and multiplayer coverage, with `pytest backend/tests/ -v`.

---

## 📄 License

This project is licensed under the **MIT License**.

<div align="center">
  <sub>Developed with ⚡ for competitive cyber-commanders worldwide.</sub>
</div>