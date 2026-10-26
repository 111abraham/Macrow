# Macrow Desktop

A high-performance, OS-level desktop macro automation tool for Windows. It captures, records, and replays pixel-accurate mouse and keyboard actions across **any desktop application** (trading platforms, browsers, games, desktop apps, etc.) using real OS-level input simulation.

---

## 🚀 Quick Start

### Option A: Run Standalone Executable (No Python Required)
Run the single-file executable directly:
```
dist/Macrow.exe
```

### Option B: Run from Source
```powershell
uv venv --python 3.11 .venv
.venv\Scripts\activate
uv pip install -r requirements.txt
python main.py
```

### Option C: Rebuild Executable
```powershell
python build.py
```

---

## 🎯 Key Features

### 1. Floating, Resizable & Always-on-Top Panel
- **Always-on-Top**: Floats above all windows and full-screen applications.
- **Effortless Edge Resizing**: Generous 10px grab zone around all borders plus a dedicated bottom-right resize grip (`QSizeGrip`).
- **Live Cursor Readout**: Continuous real-time `(X, Y)` coordinate readout on the title bar that keeps updating across the screen and over the panel itself.
- **Clickable Opacity Slider**: Adjust transparency from 20% to 100% to see charts and windows behind it—the panel **remains 100% clickable at any opacity level**.
- **Collapsible Title Bar (Minimize `—`)**: Click `—` to collapse the body into just the compact title bar displaying current coordinates. Click `□` to restore. Remembers size and minimized state across restarts.
- **Smooth Mouse Wheel Scrolling**: Scroll the mouse wheel anywhere over the panel to browse controls smoothly.

### 2. Low-Level Macro Recorder
- **Low-Level Windows Hook (`WH_MOUSE_LL` & `WH_KEYBOARD_LL`)**: Captures mouse and keyboard input at the OS kernel level, ensuring widgets calling `preventDefault()` cannot suppress clicks or drags.
- **Smooth Drag & Move Throttling**:
  - Mouse moves: throttled to ~40ms (25 FPS) when idle.
  - While dragging (mouse button held down): throttled to ~16ms (~60 FPS) for smooth drag curves.
- **Rich Event Capture**: Mouse down/up, clicks, double-clicks, mouse wheel (`x`, `y`, `deltaX`, `deltaY`), and keystrokes.
- **Synthetic Event Filtering**: Tags all synthetic inputs with signature `0x50434C4B` (`'PCLK'`). Automated actions or playback steps are never re-recorded.
- **Self-UI Exclusion**: Clicks on Macrow's own panel are automatically ignored during recording.
- **Password Protection**: Detects password input fields (`ES_PASSWORD`) and skips sensitive credential recording.
- **Max Step Safeguard**: 6000-step ceiling to prevent runaway memory usage.
- **Naming Dialog**: Prompt with pre-filled names (`Macro 1`, `Macro 2`...), where **Enter** saves and **Esc** discards.

### 3. Macro Playback Engine (Speed, Loop & Repeat X Times)
- **Accurate Relative Timing**: Replays steps using exact original relative `dt` timing.
- **Speed Slider (0.25x to 3.0x)**: Fast-forward or slow-down macro execution.
- **Repeat Options**:
  - **Repeat until Stop (loop)**: Continuously loops the macro until you click Stop or press `Alt + S`.
  - **Repeat X Times**: Enter a custom number of repetitions (e.g., 2, 5, 100). The status badge tracks progress (e.g. `Pass 2/5 (18/84)`).
- **Built-in Click-Through to App During Playback (See-Through Mode)**:
  - Hard-coded by default: as soon as you press Play, the panel automatically becomes **100% click-through** (`WS_EX_TRANSPARENT`)!
  - Real OS mouse clicks and drags pass directly through the panel to the trading chart, browser, or game underneath as if the panel isn't even there!
  - You can still see the coordinates and playback status HUD on screen without any clicks being blocked or intercepted.
  - When playback finishes or when **Alt + S** (or **F12**) is pressed, click-through is instantly disabled and normal interactive controls return immediately.
- **Visual Red Dot Indicator**: A non-activating, click-through overlay displays a pulsing red dot at the exact click location during playback.
- **Fluid Drags**: Drags replay with held mouse button states and intermediate trajectory steps.

### 4. 2-Key Emergency Stop & Safety
- **2-Key Emergency Stop (`Alt + S`)**:
  Press **Alt + S** (or **F12**, or **Ctrl + Q**) from any application to immediately halt macro playback and release all held mouse buttons. **It safely stops playback without closing the application!**
- **Screen Corner Failsafe**: Slamming the physical mouse cursor into the top-left corner `(0, 0)` immediately halts all automations.
- **Global Shortcuts**:
  - `Alt + S` (or `F12`): Emergency Stop (halts playback safely)
  - `Ctrl + F9` (or `F9`): Start / Stop Recording
  - `Ctrl + F8` (or `F8`): Play / Pause / Resume Playback
  - `Ctrl + F7` (or `F7`): Stop Playback

### 5. JSON Export & Import (Extension Compatible)
- **Export**: Exports all macros to a dated `.json` file (`macrow-macros-YYYY-MM-DD.json`).
- **Collision Handling**: Merges imported macros cleanly without overwriting; appends `(2)`, `(3)`, etc. on name collisions.
- **Extension Viewport Alignment Wizard**: Lets you keep coordinates, enter an offset `(dx, dy)`, or click a reference point on screen to translate browser-viewport coordinates to desktop coordinates.

### 6. Multi-Instance Support & Queue Scheduler
- Click `+` on the title bar to spawn independent Macrow panels.
- Each instance maintains its own selected macro, playback speed, repeat options, and position.
- **Single-Cursor FIFO Scheduler**: Coordinates physical mouse cursor access among instances so macros don't fight over the pointer.
