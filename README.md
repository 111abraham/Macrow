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
- **Effortless 8-Direction Edge Resizing**: Generous grab zone around all borders—including top edge, corners, sides, and dedicated bottom-right grip (`QSizeGrip`).
- **Multi-Screen & Maximize / Restore (`□` / `❐`)**: Full maximize support in the title bar that adapts to any monitor size without artificial width/height warping. Double-clicking the title bar toggles maximize / restore.
- **Dock-to-Top Aero Snap & Smooth Tear-Off**: Drag the title bar to the top edge of any monitor to automatically snap to full screen; drag downward smoothly to restore floating window size centered on the cursor without crashing.
- **Live Cursor Readout**: Continuous real-time `(X, Y)` coordinate readout on the title bar that keeps updating across the screen and over the panel itself.
- **Clickable Opacity Slider**: Adjust transparency from 20% to 100% to see charts and windows behind it—the panel remains interactive at any opacity level.
- **Native Taskbar Integration & Clean Minimization**: Configured with `WS_EX_APPWINDOW` and DWM styles. Minimizes cleanly into the Windows taskbar without leaving residual bottom-left boxes.
- **Smooth Mouse Wheel Scrolling**: Scroll the mouse wheel anywhere over the panel to browse controls smoothly.
- **Independent Taskbar Entry for Node Customizer**: When opened simultaneously with Macrow, the Node Customizer has its own independent taskbar button and icon for effortless multitasking.

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

### 3. Macro Playback Engine (Speed, Loop, Pause/Stop & Click-Through)
- **Accurate Relative Timing & Interruption**: Replays steps using exact relative `dt` timing with sliced responsive delays (checks stop/pause signals every 15ms).
- **Fully Interactive Pause & Stop Buttons**: The Pause and Stop buttons are 100% clickable and responsive at all times during playback.
- **Optional Click-Through Overlay**: Toggleable `Click-through overlay` checkbox allows clicks to pass directly through the panel to the game or desktop beneath whenever desired (`Alt+S` or `F12` to halt).
- **Speed Slider (0.25x to 3.0x)**: Fast-forward or slow-down macro execution.
- **Repeat Options**:
  - **Repeat until Stop (loop)**: Continuously loops the macro until you click Stop or press `Alt + S`.
  - **Repeat X Times**: Enter a custom number of repetitions (e.g., 2, 5, 100). The status badge tracks progress (e.g. `Pass 2/5 (18/84)`).
- **Visual Red Dot Indicator**: A non-activating overlay displays a pulsing red dot at the exact click location during playback.
- **Fluid Drags**: Drags replay with held mouse button states and intermediate trajectory steps.

### 4. 2-Key Emergency Stop & Safety
- **2-Key Emergency Stop (`Alt + S`)**:
  Press **Alt + S** (or **F12**, or **Ctrl + Q**) from any application to immediately halt macro playback and release all held mouse buttons. **It safely stops playback without closing the application!**
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

### 7. Visual Node Flow Editor & Automation Customizer
Macrow includes a visual node-based macro customizer (Node Editor) that translates raw recorded macros into interactive flowchart graphs and compiles graphs back into high-speed automation scripts.

- **🧱 Lego Mindstorms-Style C-Clamp Repeat Zone**:
  - **Dual Jaw Bracket Architecture**: Top arm accepts input (`In`) and feeds into the loop's internal mouth (`Body`). Bottom shelf provides `Loop In` and the loop termination exit socket (`Done`).
  - **Automatic Dynamic Bounding**: The bracket automatically resizes its mouth horizontally and vertically to cleanly frame all enclosed action nodes.
  - **Nested Repeat Zones**: Place repeat zones inside other repeat zones (C-clamp inside C-clamp). Scoped containment prevents outer loop translations from double-moving or displacing inner body nodes.
  - **Auto-Cycle Body Flow**: The end of a loop body sequence automatically cycles back into the loop start without requiring a clutter of backwards return wires.
  - **Infinite vs. Counted Modes**: Toggle between infinite loops (`∞`) and precise iteration counts with custom index variables (`$i`, `$row`, `$wave`).

- **🎛️ Universal Parameter Inputs & Macro-Wide Variable Memory**:
  - **Default Integer Typing (`123 Int ▾`)**: Parameter inputs default to integer type with quick mouse wheel scrubbing (scroll up/down to step values, hold `Shift` for x10).
  - **Dynamic Syntax Badging**: Visual badge automatically transforms between `123 Int ▾`, `0.0 Float ▾`, `abc Str ▾`, and `$ Var ▾` based on input value.
  - **Macro-Wide Custom Variable Memory**: Any custom variable defined in a Math node, Loop counter, or typed anywhere (e.g. `$target_hp`, `$row`, `$slot`) is automatically remembered macro-wide and appears in the variable picker dropdown of every node in that macro.
  - **Undo/Redo Persistence**: Custom variable registers persist through serialization, deserialization, undo (`Ctrl+Z`), and redo (`Ctrl+Y`).

- **🧩 Complete 18+ Node Action & Logic Suite**:
  - **Mouse Actions**: Click, Double Click, Mouse Down (Hold), Mouse Up (Release), Mouse Move (Smooth curve trajectory or Direct Jump), Mouse Wheel Scroll.
  - **Keyboard Actions & Full Key Catalog**:
    - **Key Press (Tap)**: Presses and releases any key with accurate timing.
    - **Key Down (Hold)**: Holds down any key continuously. Auto-repeat typematic pulses (every 45ms) are **enabled by default** for seamless gaming and movement.
      - **Until Release Mode (`Hold Duration = 0`)**: The key is held (and pulsed in the background) while subsequent nodes execute. It remains active until explicitly released by a companion **Key Up (Release)** node or when playback ends!
      - **Timed Duration Mode (`Hold Duration > 0ms`)**: The node self-holds and pulses for the specified milliseconds, then automatically releases without requiring a Key Up node.
    - **Key Up (Release)**: Releases any held key and cancels any background auto-repeat pulses. Essential for ending long-running holds across branching paths, loops, and complex workflows.
    - **Complete Keyboard Coverage**: All letters (`A`–`Z`), numbers (`0`–`9`), full numeric keypad (`Num 0`–`Num 9`, `Num +`, `Num -`, `Num *`, `Num /`, `Num .`, `Num Enter`, `Num Lock`), function keys (`F1`–`F24`), navigation (`Enter`, `Esc`, `Tab`, `Space`, `Backspace`, `Delete`, `Insert`, `Home`, `End`, `Page Up`, `Page Down`), arrow keys, modifiers (`Shift`, `Ctrl`, `Alt`, `Win`, `Caps Lock`, `Scroll Lock`), symbols (`;`, `=`, `,`, `-`, `.`, `/`, `` ` ``, `[`, `\`, `]`, `'`), and media keys.
    - **Categorized Key Picker & 1-Click Quick Picks**: Categorized dropdown list plus instant 1-click pills for most common keys (`Enter`, `Space`, `Tab`, `Esc`, `Shift`, `Ctrl`, `Alt`, etc.).
    - **Type Text**: Type strings with real-time `$variable` substitution.
    - **Key Combination Hotkeys**: Multi-key combinations (`Ctrl+C`, `Ctrl+V`, `Win+D`, `Ctrl+Shift+Esc`, etc.).
  - **OS Security Restriction Handling (SAS)**: Explicit presets and options for `Ctrl+Alt+Delete` and Task Manager invocation.
  - **Logic & Branching**:
    - **If / Compare Condition**: Compare variable values against numbers or strings with `True →` and `False →` output paths.
    - **Pixel Color Verification with Togglable Bounding Box (Region Search)**:
      - **Single Coordinate Mode**: Tests the exact pixel color at `(X, Y)` with configurable tolerance (±0 to ±60).
      - **Bounding Box Region Mode**: Toggles an adjustable search window (`X`, `Y`, `Width`, `Height`) to find target colors across a wider area.
      - **Live Interactive Bounding Box Screen Highlight Overlay**: Clicking on any Pixel Color Check node in the canvas or inspector instantly highlights its exact search bounding box on your actual desktop screen! Features a non-activating, click-through overlay with vibrant dashed borders, CAD-style corner reticles, soft translucent tint, and a floating dimension pill badge (`🎨 Pixel Search Region: W×H (X, Y)`).
      - **Interactive Edge Resizing & Dragging on Desktop**: Grab any of the 8 border or corner edges on your screen to resize the bounding box dynamically (with custom cursor indications `⤡`, `⤢`, `↔`, `↕`), or drag from inside the box or badge to move it. Live changes synchronize bidirectionally with the Property Inspector inputs (`Top-Left X`, `Y`, `Width`, `Height`).
      - **Mathematically Guaranteed Off-Color Borders (Self-Detection Immune)**: Overlay border lines and corner reticles automatically calculate a mathematically inverted safe hue offset ($\Delta E \ge 260$ Manhattan RGB distance from your target color). Even with high tolerance settings, `Pixel Color Check` will never mistakenly detect the overlay's own border lines while the node is selected in the customizer! The true target color is displayed safely inside the badge swatch pill.
      - **Per-Screen Native Overlays (Zero Multi-Monitor DPI Distortion)**: Both the Bounding Box Drag tool (`ScreenSnipper`) and Color Picker (`CoordinateEyeDropper`) use an independent per-screen native canvas architecture. Each monitor is sampled 1:1 at its native hardware resolution, completely eliminating mixed-DPI scaling issues (such as secondary 100% DPI screens vs primary 125% DPI displays causing shrinking to the top-left or color picking offsets).
      - **Floating Dimension & Swatch Badge Situated Outside Search Area**: The floating pill badge (`RegionBadgeOverlay`) with the dimension readout (`67×1`) and target color preview swatch is positioned strictly **outside** the main bounding box (floating 4px above the top-left edge, or below if near the monitor top). The interior of the search rectangle contains zero swatches or badges, completely eliminating false positives where Pixel Color Check would detect its own swatch!
      - **Instant Node-to-Node Property Inspector Switching**: Clicking directly on any node on the canvas instantly focuses it as the active item and populates the Property Inspector with its specific settings immediately—no need to click off or deselect first.
      - **Guaranteed Click Capture in Color Picker (`CoordinateEyeDropper`)**: The Eye Dropper overlay displays a 1:1 unscaled hardware desktop screenshot as a solid surface, ensuring mouse clicks never punch through to background applications. Combined with OS-level click detection (`GetAsyncKeyState`), clicking to sample pixel coordinates and colors is 100% reliable.
      - **Multi-Monitor & DPI-Accurate Capture (No Left Shift)**: Seamlessly accounts for multi-screen setups, negative coordinate offsets, and Per-Monitor Windows DPI scaling. Both the capture engine and screen overlay map 1:1 to your exact desktop pixels without horizontal or vertical offset distortion.
      - **Visual Screen Selection**: Click `📐 Drag Bounding Box on Screen` to drag and frame the search area directly over your desktop. Automatically samples the target color.
      - **Auto-Coordinate Extraction**: When a matching pixel is found in the box, routes to `Match →` and immediately exports its exact global screen coordinates to `$pixel_x` and `$pixel_y` for downstream clicks or moves!
      - **Vectorized Performance**: Scans large screen areas in under 1 millisecond via vectorized NumPy Manhattan color distance.
    - **Math & Variable Assignment**: Increment (`+= 1`), Decrement (`-= 1`), Set (`= value`), Add (`+= value`), Subtract, Multiply, and Random range (`rand(min..max)`).
    - **Vision AI / Screen Search with Multi-Template OR Recognition**:
      - **Instant Parallel OR Detection**: Add multiple template variants (e.g. single cactus, double cactus, triple cactus) to a single `Wait For Image` node via `➕ Snip Variant (OR)`. All templates are matched against a single frame in parallel in ~3ms.
      - **In-Memory Grayscale Cache**: PNGs are decoded once and cached in memory, eliminating redundant disk I/O and boosting frame rates.
      - **Early Scale-1 Exit & High-Frequency Polling**: Evaluates every 30ms (~33 FPS) with instant 1:1 match detection, delivering ultra-low latency reaction times for fast runner games.
      - **Variant Manager**: Visual gallery in the Property Inspector to inspect each template and remove variants (`✖`) with one click.
    - **Stop Playback**: Explicit termination node.

- **🪄 Houdini-Inspired Canvas Gestures**:
  - `Tab`: Opens Quick-Add Node popup directly under the mouse cursor.
  - `Y + Drag`: Knife tool with glowing crimson laser trail to sever wires.
  - `A + Drag`: Aligns upstream or downstream connected branches horizontally.
  - `Ctrl + Drag` / `Shift + Drag`: Moves entire downstream or upstream connected branches.
  - `B`: Toggles bypass on selected node(s).
  - `Alt + Click/Drag`: Duplicates selected node(s) in-place.
  - Rapid Shake: Shaking a connected node rapidly unplugs it from its wires.
  - Wire Auto-Splice: Dropping an unconnected node onto a wire splices the node in-between.
  - Interactive Snap Wire: Dynamic candidate socket glow when wire tip approaches.

- **📚 Varied Real-World Example Presets**:
  1. **📋 Form Auto-Filler & Exporter**: Minimizes to desktop, double-clicks document, types variable text (`Record #$row: Complete`), advances fields with Tab, and saves with `Ctrl+S`.
  2. **🎮 Boss Combat Guard**: Outer combat loop, pixel color HP bar monitor, Vision AI target recognition, mana condition evaluation, ability clicks, and camera zoom scroll.
  3. **🖱️ Inventory Drag-and-Drop Sorter**: Coordinate math initialization, mouse down grab, smooth drag move, mouse up release, coordinate stepping, and delay.
  4. **⚡ Discrete Key Hold & Multi-Select**: Key down Shift hold, shift-click multi-selection, key up Shift release, and clipboard copy hotkeys.
  5. **🔄 Nested Loops & Coordinate Grid**: Nested C-clamp repeat zone within C-clamp repeat zone, mathematical cell indexing, and row progression.
