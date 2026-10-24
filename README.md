<div align="center">

# ⚡ NEON FOUR CHESS ⚡
### *The Cybernetic 4-Player Tactical Chess Arena*

[![Python](https://img.shields.io/badge/Python-3.14%2B-00f3ff?style=for-the-badge&logo=python&logoColor=black)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-ff007f?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![WebSockets](https://img.shields.io/badge/WebSockets-Real--Time-39ff14?style=for-the-badge&logo=websocket&logoColor=black)](https://websockets.readthedocs.io/)
[![Capacitor](https://img.shields.io/badge/Capacitor-Android%20Ready-ffd700?style=for-the-badge&logo=capacitor&logoColor=black)](https://capacitorjs.com/)
[![Tests](https://img.shields.io/badge/Tests-14%20Passed-00f3ff?style=for-the-badge&logo=pytest&logoColor=black)](backend/tests/)
[![License](https://img.shields.io/badge/License-MIT-ffffff?style=for-the-badge)](LICENSE)

<br/>

**Neon Four Chess** is a high-octane, four-player tactical chess battleground built on an authentic **14×14 cross-shaped arena**. Featuring server-authoritative move validation, zero-latency WebSockets multiplayer, pass-and-play local combat, synthesized Web Audio sound effects, and native Android packaging with Capacitor.

[🎮 Features](#-key-features) • [📜 Rules of Engagement](#-rules-of-engagement) • [🗺️ Board Architecture](#️-board-architecture) • [⚔️ Commanders](#️-the-four-neon-commanders) • [🚀 Quickstart](#-quickstart-guide) • [📱 Android Build](#-android-build--deployment) • [📡 API & WebSockets](#-api--websocket-protocol)

---

</div>

## 🎮 Key Features

| Mode / System | Description |
|---|---|
| **⚔️ 4-Player Cross Arena** | Authentic 14×14 grid with 3×3 corner voids (160 active squares) and 4 symmetric armies. |
| **🌐 Real-Time Multiplayer** | Instant room creation with 6-character room codes (`NEON42`), live WebSocket turn sync, and presence tracking. |
| **🛡️ Authoritative Backend** | Python FastAPI engine validates every move, turn order, castling right, and promotion server-side. |
| **📱 Local Pass & Play** | Play with 4 commanders on a single mobile device or desktop with optional turn-privacy shields and move undo. |
| **🔊 Synthesized Web Audio** | Pure procedural sci-fi audio effects (movement chime, laser capture zap, alarm check pulse, victory synth fanfare) with zero external assets. |
| **🤖 Capacitor Android Ready** | Native Android project with custom app icons, cyberpunk splash screens, and LAN configuration for physical phones. |
| **🔄 Dynamic Board Rotation** | Rotate the board manually by 90° or enable auto-rotation to align with the active commander's perspective. |
| **💬 Tactical Quick Chat** | In-game neon emote toasts (*"Check!"*, *"Good move!"*, *"GG!"*) for real-time multiplayer banter. |

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

## ⚔️ The Four Neon Commanders

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
│       ├── icon.png             # Neon 4-player chess app icon (1:1)
│       └── splash.png           # Cyberpunk mobile splash screen (9:16)
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
| `GET` | `/rooms/{code}` | Retrieve full serialized board state & active players |
| `POST` | `/rooms/{code}/move` | Authoritative move submission |
| `POST` | `/rooms/{code}/resign` | Resign current player |
| `POST` | `/rooms/{code}/reset` | Rematch & reset board |
| `GET` | `/api/history` | Match log of completed games |

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
  "room_code": "NEON42",
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

---

## 🔬 Testing & Quality Assurance

All core features are verified through automated tests:

```powershell
pytest backend/tests/ -v
```

```
============================== test session starts ==============================
collected 14 items

backend/tests/test_api.py::test_health_check PASSED                       [  7%]
backend/tests/test_api.py::test_create_and_join_room_flow PASSED          [ 14%]
backend/tests/test_api.py::test_server_authoritative_move_validation PASSED [ 21%]
backend/tests/test_api.py::test_resign_flow PASSED                        [ 28%]
backend/tests/test_engine.py::test_board_geometry_and_voids PASSED        [ 35%]
backend/tests/test_engine.py::test_initial_piece_setup PASSED             [ 42%]
backend/tests/test_engine.py::test_pawn_forward_and_double_step PASSED    [ 50%]
backend/tests/test_engine.py::test_knight_movement_over_pieces PASSED     [ 57%]
backend/tests/test_engine.py::test_pawn_captures PASSED                   [ 64%]
backend/tests/test_engine.py::test_pawn_promotion PASSED                  [ 71%]
backend/tests/test_engine.py::test_king_check_detection PASSED            [ 78%]
backend/tests/test_engine.py::test_castling_cyan PASSED                   [ 85%]
backend/tests/test_engine.py::test_elimination_and_dormant_pieces PASSED  [ 92%]
backend/tests/test_websockets.py::test_websocket_sync_and_ping PASSED     [100%]

======================== 14 passed, 41 warnings in 1.35s ========================
```

---

## 📄 License

This project is licensed under the **MIT License**.

<div align="center">
  <sub>Developed with ⚡ for competitive cyber-commanders worldwide.</sub>
</div>