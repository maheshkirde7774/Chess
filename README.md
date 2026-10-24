# ⚡ Neon Four Chess

**Neon Four Chess** is a cybernetic, futuristic 4-player chess game designed with a neon gaming aesthetic. It features a full-fledged 14×14 cross-shaped chessboard variant, local pass-and-play, real-time online multiplayer over WebSockets, a Python FastAPI backend with SQLite persistence, and an Android project packaged with Capacitor.

---

## 🎮 Features Overview

- **Authentic 14×14 Cross Arena**: 160 active squares with 4 cut-out 3×3 corners.
- **Four Distinct Neon Armies**:
  - **Player 1**: Cyan (`#00f3ff`) — South (Bottom)
  - **Player 2**: Magenta (`#ff007f`) — West (Left)
  - **Player 3**: Lime Green (`#39ff14`) — North (Top)
  - **Player 4**: Gold (`#ffd700`) — East (Right)
- **Genuine 4-Player Ruleset**:
  - Clockwise turn order: Cyan → Magenta → Lime → Gold.
  - Dynamic pawns advancing towards the center with initial 2-step push and diagonal captures.
  - **8th-Rank Pawn Promotion**: Pawns promote to Queen, Rook, Bishop, or Knight upon reaching the 8th rank from their starting position or opposite perimeter.
  - Castling support for all 4 commanders.
  - **Check & Checkmate Detection**: Players in check must make an escape move; otherwise, they are eliminated.
  - **Dormant Neutral Army**: When a player is eliminated or resigns, their King is removed and remaining pieces become neutral obstacles that can be captured by other active players.
  - **Last Commander Standing**: The last remaining player with their King intact is declared victor.
- **Local Mode (Pass & Play)**:
  - 4 players play on the same phone or tablet.
  - Optional Pass-Device privacy screen ("Pass phone to Magenta — Tap to Reveal").
  - Move undo support for local games.
  - Board rotation (manual 90° or auto-rotate to current player's perspective).
- **Online Multiplayer**:
  - Create room with unique 6-character room codes (e.g., `NEON42`).
  - Join rooms across different devices.
  - Real-time move synchronization via FastAPI WebSockets (`/ws/{room_code}`).
  - Server-authoritative move validation (protects against illegal moves and unauthorized turns).
  - Automatic reconnection handling and heartbeat pings.
  - Quick-chat tactical emotes (*"Check!"*, *"Good move!"*, *"GG!"*).
- **Synthesized Web Audio API Sound System**:
  - Sci-fi move chime, laser capture zap, dual-pulse check alarm, and ascending synth victory fanfare with zero external audio assets.
- **Capacitor Android Packaging**:
  - Pre-configured Android project in `android/`.
  - Custom neon cyberpunk app icon and splash screens across all screen densities.
  - Android network permissions (`INTERNET`, `ACCESS_NETWORK_STATE`, and cleartext HTTP for local LAN testing).
  - Configurable backend server URL via Settings modal.

---

## 🛠️ Technology Stack

| Layer | Technology | Details |
|---|---|---|
| **Frontend** | HTML5, Vanilla CSS, Modern ES6+ JavaScript | Responsive 14×14 grid, custom SVG vector pieces with neon glow filters, Web Audio API |
| **Backend** | Python 3.14+, FastAPI, Uvicorn | REST API, WebSockets Connection Manager, server-authoritative engine |
| **Chess Engine** | Custom 4-Player Chess Engine | Complete move generation, pins, checks, castling, promotion, elimination |
| **Database** | SQLite & SQLAlchemy ORM | Room state persistence and completed match history |
| **Mobile App** | Capacitor 6 | Android wrapper, native project in `android/` |
| **Testing** | pytest | 14 automated unit and integration tests |

---

## 📁 Project Structure

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

## 🚀 Getting Started

### 1. Prerequisites

- **Python 3.10+** (tested on Python 3.14)
- **Node.js 18+** & **npm**

### 2. Python Backend Setup

1. Install Python dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

2. Run automated test suite:
   ```bash
   pytest backend/tests/
   ```
   *(All 14 tests covering engine rules, REST endpoints, and WebSockets will run and pass).*

3. Start the FastAPI backend server:
   ```bash
   python backend/run.py
   ```
   The backend will start at `http://127.0.0.1:8000`.
   - Access the interactive API docs at `http://127.0.0.1:8000/docs`.
   - Access the live playable game directly at `http://127.0.0.1:8000/`.

---

## 📱 Playing the Game

### Local Pass & Play
1. Open the game in any mobile browser or desktop browser.
2. Select **Local Pass & Play** from the menu.
3. Players take turns starting with **Cyan (South)**.
4. Click on any piece of the current active army to reveal legal move dots and capture rings.
5. Tap an indicator to execute the move.
6. Optional Settings:
   - **Pass Device Privacy Screen**: When enabled, hides the board between turns until the next player taps "Reveal Board".
   - **Auto-Rotate**: Automatically rotates the board 90° each turn to face the current player.

### Online Multiplayer
1. Player 1 selects **Create Online Room**, enters their Commander Name, and receives a unique 6-character room code (e.g., `NEON42`).
2. Players 2, 3, and 4 select **Join Online Room**, input the code, and choose their Commander Name.
3. Player roles are assigned automatically in order:
   - Player 1: Cyan (South)
   - Player 2: Magenta (West)
   - Player 3: Lime (North)
   - Player 4: Gold (East)
4. Moves are validated authoritatively on the backend and broadcast in real time to all connected players. Unauthorized players cannot move other players' armies.

---

## 🤖 Android Build & Mobile Instructions

The frontend is packaged as an Android application using Capacitor.

### Configuring the Backend URL for a Real Android Phone

A real Android phone or emulator cannot access the desktop backend using `localhost`. To connect your physical phone:

1. Connect your phone to the same Wi-Fi network as your computer.
2. Find your computer's local network IP address:
   - Windows PowerShell: `ipconfig` (Look for IPv4 Address, e.g., `192.168.1.50`).
3. In the game on your phone:
   - Tap the **⚙ Settings** icon in the top right.
   - Enter your computer's LAN address in the **Backend Server URL** field (e.g., `http://192.168.1.50:8000`).
   - Tap **Test** to verify connection, then tap **Save Preferences**.
   - Your preference is saved in `localStorage` across app restarts.

### Building a Debug APK

1. Ensure Android Studio and JDK 17+ are installed.
2. Sync web assets into the Android native project:
   ```bash
   npx cap sync
   ```
3. Open the project in Android Studio:
   ```bash
   npx cap open android
   ```
4. Build the debug APK:
   - **Via Command Line**:
     ```bash
     cd android
     ./gradlew assembleDebug
     ```
     The APK will be generated at:
     `android/app/build/outputs/apk/debug/app-debug.apk`
   - **Via Android Studio**:
     Go to `Build` > `Build Bundle(s) / APK(s)` > `Build APK(s)`.

---

## 📜 Four-Player Chess Rules Documented

1. **Board Geometry**: 14×14 grid with 3×3 corners voided out. Total active squares = 160.
2. **Armies**: Each army starts with 8 back-rank pieces (R, N, B, Q, K, B, N, R) and 8 pawns.
3. **Turn Order**: Cyan (1) → Magenta (2) → Lime (3) → Gold (4).
4. **Pawn Movement**: Pawns advance towards the center. On their initial turn, pawns can move 1 or 2 squares. Diagonal captures are forward-relative to each army's advance direction.
5. **Promotion**: Pawns promote to Queen, Rook, Bishop, or Knight upon reaching the 8th rank relative to their home rank, or any edge square where forward advance is blocked.
6. **Check & Pins**: A player whose King is threatened by any active opponent must escape check. Pieces pinned to the King cannot move into paths that expose the King.
7. **Elimination**: If a player is checkmated or resigns:
   - Their King is removed from the board.
   - Their remaining pieces become **neutral/dormant obstacles** (they cannot move or threaten other players, but can be captured).
   - Turn order permanently skips eliminated players.
8. **Victory**: The last surviving player is declared the Champion.

---

## 🔬 Testing & Verification

Automated unit and integration tests are located in `backend/tests/`:
- `test_engine.py`: Validates board geometry, piece counts, pawn pushes, captures, promotions, knight jumps, checks, pins, castling, and elimination.
- `test_api.py`: Validates room creation, joining, seat assignment, full-room rejection, server-authoritative move validation, and resignation.
- `test_websockets.py`: Validates real-time state synchronization, ping/pong heartbeats, and move broadcasting over WebSockets.

Run tests:
```bash
pytest backend/tests/ -v
```

---

## ⚠️ Known Limitations & External Dependencies

1. **Local APK Compilation**: Generating the standalone `.apk` binary requires an installed Java Development Kit (JDK 17+) and Android SDK / Android Studio on the host machine. The Capacitor native project and all resource icons are fully generated and ready in `android/`.
2. **Browser Automation Sandbox**: In the current headless container environment, `open_browser_url` timed out due to system-level browser display limitations. The application runs and serves HTTP 200 responses reliably on `http://127.0.0.1:8000/`.
3. **En Passant**: Omitted to keep 4-player simultaneous interactions deterministic and avoid multi-turn timing conflicts.
