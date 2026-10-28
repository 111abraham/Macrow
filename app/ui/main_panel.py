"""
Floating, draggable, always-on-top Main Panel for Macrow Desktop.
Focused exclusively on OS-level Macro Recording, Playback (with Speed, Loop & Repeat X Times),
and JSON Export/Import with effortless edge-resizing and smooth scrolling.
"""

import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QCheckBox,
    QComboBox,
    QScrollArea,
    QFrame,
    QFileDialog,
    QMessageBox,
    QApplication,
    QSizeGrip,
    QSizePolicy,
    QMenu,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import QIcon, QCursor, QGuiApplication

from app.core.win32_api import get_cursor_pos, init_dpi_awareness, set_window_click_through
from app.core.input_simulator import InputSimulator
from app.core.recorder import MacroRecorder
from app.core.player import MacroPlayer
from app.core.scheduler import GLOBAL_SCHEDULER
from app.ui.styles import DARK_THEME_QSS
from app.ui.indicator import VisualIndicator
from app.ui.name_dialog import MacroNameDialog
from app.ui.import_dialog import ImportWizardDialog
from app.ui.node_editor import MacroNodeEditorWindow
from app.ui.assets import get_app_icon, get_app_pixmap


class BridgeSignals(QObject):
    step_count_updated = pyqtSignal(int)
    max_steps_reached = pyqtSignal()
    player_state_changed = pyqtSignal(str)
    player_progress = pyqtSignal(int, int)
    pass_progress = pyqtSignal(int, int)
    cursor_action = pyqtSignal(int, int, str)
    scheduler_status = pyqtSignal(str)


class MacrowPanel(QWidget):
    """Main floating automation panel for Macrow."""

    new_window_requested = pyqtSignal()

    RESIZE_MARGIN = 10  # Generous 10px grab zone for effortless edge resizing

    def __init__(self, config_manager, instance_id=1, simulator=None):
        super().__init__()
        self.cfg = config_manager
        self.instance_id = str(instance_id)
        self.sim = simulator or InputSimulator()

        # Engines
        self.recorder = MacroRecorder(own_pid=os.getpid())
        self.player = MacroPlayer(self.sim)
        self.indicator = VisualIndicator()

        # Thread bridges
        self.bridges = BridgeSignals()
        self._init_bridges()

        # Drag & Resize state
        self._is_dragging = False
        self._is_resizing = None
        self._drag_start_pos = QPoint()
        self._resize_start_pos = QPoint()
        self._resize_start_geom = None
        self._unminimized_height = 420
        self._current_pass = 1
        self._total_passes = 1

        # Build UI
        self._init_window()
        self._init_ui()
        self._install_resize_filters()
        self._restore_settings()

        # Shared configuration changes
        self.cfg.add_change_listener(self._on_shared_config_changed)
        GLOBAL_SCHEDULER.register_instance(self.instance_id, self._on_scheduler_status)

        # Polling timer for live cursor coordinates
        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self._update_cursor_readout)
        self.cursor_timer.start(35)

    def _init_bridges(self):
        # Recorder callbacks -> Qt signals
        self.recorder.on_step_count_changed = lambda count: self.bridges.step_count_updated.emit(count)
        self.recorder.on_max_steps_reached = lambda: self.bridges.max_steps_reached.emit()
        self.bridges.step_count_updated.connect(self._on_recorder_step_count)
        self.bridges.max_steps_reached.connect(self._on_recorder_max_steps)

        # Player callbacks -> Qt signals
        self.player.on_state_changed = lambda state: self.bridges.player_state_changed.emit(state)
        self.player.on_progress = lambda cur, tot: self.bridges.player_progress.emit(cur, tot)
        self.player.on_pass_progress = lambda cur, tot: self.bridges.pass_progress.emit(cur, tot)
        self.player.on_cursor_action = lambda x, y, act: self.bridges.cursor_action.emit(x, y, act)
        self.bridges.player_state_changed.connect(self._on_player_state_changed)
        self.bridges.player_progress.connect(self._on_player_progress)
        self.bridges.pass_progress.connect(self._on_pass_progress)
        self.bridges.cursor_action.connect(self._on_cursor_action)

        # Scheduler status
        self.bridges.scheduler_status.connect(self._update_scheduler_status_ui)

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowIcon(get_app_icon())
        self.setStyleSheet(DARK_THEME_QSS)

        # Minimum dimensions: compact and flexible
        self.setMinimumSize(280, 160)
        self.setMouseTracking(True)

        screen = QGuiApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            avail_w = avail.width()
            avail_h = avail.height()
            self.setMaximumWidth(min(700, avail_w - 40))
            self.setMaximumHeight(max(300, avail_h - 40))
            default_h = max(260, min(440, avail_h - 100))
        else:
            default_h = 440

        self.resize(320, default_h)
        self._unminimized_height = default_h

    def _init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(4, 4, 4, 4)  # 4px margin gives clean edge-grab zone

        self.main_container = QFrame(self)
        self.main_container.setObjectName("MainContainer")
        self.main_container.setMouseTracking(True)
        container_layout = QVBoxLayout(self.main_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Title bar
        self.title_bar = self._create_title_bar()
        container_layout.addWidget(self.title_bar)

        # Scrollable body
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area.setMouseTracking(True)

        self.body_widget = QWidget()
        self.body_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self.body_widget.setMouseTracking(True)
        body_layout = QVBoxLayout(self.body_widget)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(8)

        # Reordered: Opacity -> Playback (FIRST!) -> Recorder -> Export/Import
        body_layout.addWidget(self._create_opacity_section())
        body_layout.addWidget(self._create_macro_playback_section())
        body_layout.addWidget(self._create_macro_recorder_section())
        body_layout.addWidget(self._create_export_import_section())

        self.scroll_area.setWidget(self.body_widget)
        container_layout.addWidget(self.scroll_area)

        # Footer bar with 2-key shortcut reminder & corner resize grip
        self.footer_bar = self._create_footer_bar()
        container_layout.addWidget(self.footer_bar)

        outer_layout.addWidget(self.main_container)

    def _install_resize_filters(self):
        """Install event filters on container and scroll viewport to guarantee edge-drag resizing."""
        self.main_container.installEventFilter(self)
        self.scroll_area.installEventFilter(self)
        self.scroll_area.viewport().installEventFilter(self)
        self.body_widget.installEventFilter(self)

    def _create_title_bar(self):
        bar = QFrame(self)
        bar.setObjectName("TitleBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # Application icon in title bar
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(18, 18)
        self.icon_lbl.setScaledContents(True)
        self.icon_lbl.setPixmap(get_app_pixmap(18))
        layout.addWidget(self.icon_lbl)

        title_text = "Macrow"
        self.title_lbl = QLabel(title_text)
        self.title_lbl.setObjectName("AppTitle")
        layout.addWidget(self.title_lbl)

        # Live cursor coordinates pill readout
        self.coords_pill = QLabel("X: ---  Y: ---")
        self.coords_pill.setObjectName("CoordsPill")
        layout.addWidget(self.coords_pill)

        layout.addStretch()

        # Shortcuts dropdown button (replaces '+' button)
        self.help_btn = QPushButton("?")
        self.help_btn.setObjectName("TitleBtn")
        self.help_btn.setToolTip("Keyboard Shortcuts & Help (?)")
        self.help_btn.clicked.connect(self._show_shortcuts_menu)
        layout.addWidget(self.help_btn)

        # Minimize to taskbar button
        self.min_btn = QPushButton("—")
        self.min_btn.setObjectName("TitleBtn")
        self.min_btn.setToolTip("Minimize Macrow to taskbar")
        self.min_btn.clicked.connect(self.showMinimized)
        layout.addWidget(self.min_btn)

        # Close button
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("TitleBtn")
        self.close_btn.setStyleSheet("#TitleBtn:hover { background-color: #ef4444; color: white; }")
        self.close_btn.setToolTip("Close this instance")
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        return bar

    def _build_shortcuts_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #18181b;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 4px;
                color: #e4e4e7;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                font-size: 11px;
            }
            QMenu::item {
                padding: 5px 22px 5px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #27272a;
                color: #38bdf8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #27272a;
                margin: 4px 6px;
            }
            QMenu::section {
                padding: 4px 10px;
                font-weight: 700;
                font-size: 10px;
                color: #38bdf8;
                letter-spacing: 0.5px;
            }
        """)

        # Section: Global & Macro Controls
        menu.addSection("GLOBAL & MACRO SHORTCUTS")

        act_rec = menu.addAction("● Record Macro (Start / Stop)\tF9 / Ctrl+F9")
        act_rec.triggered.connect(self.toggle_recording)

        act_play = menu.addAction("▶ Play / Pause Macro\tF8 / Ctrl+F8")
        act_play.triggered.connect(lambda: self.toggle_pause() if self.player.is_playing() else self.start_playback())

        act_stop = menu.addAction("⏹ Stop Playback\tF7 / Ctrl+F7")
        act_stop.triggered.connect(self.stop_playback)

        act_halt = menu.addAction("🛑 Emergency Stop\tAlt+S / F12")
        act_halt.triggered.connect(self.stop_playback)

        act_kill = menu.addAction("⚡ Safety Kill Switch\tCtrl+Alt+Esc")
        act_kill.triggered.connect(self.stop_playback)

        menu.addSeparator()

        # Section: Node Graph Editor
        menu.addSection("NODE GRAPH EDITOR SHORTCUTS")

        menu.addAction("🎯 Center / Frame View\tR")
        menu.addAction("☑ Select All Nodes\tCtrl+A")
        menu.addAction("🚫 Bypass / Mute Node(s)\tB")
        menu.addAction("💾 Save & Apply\tCtrl+S")
        menu.addAction("↩ Undo Canvas\tCtrl+Z")
        menu.addAction("↪ Redo Canvas\tCtrl+Y")
        menu.addAction("📋 Copy Nodes\tCtrl+C")
        menu.addAction("📄 Paste Nodes\tCtrl+V")
        menu.addAction("⚡ Duplicate Drag\tAlt + Drag")
        menu.addAction("✂ Cut Wire (Knife)\tY + Drag")
        menu.addAction("🔌 Unplug Wire\tClick Input")
        menu.addAction("✋ Pan Canvas\tRight / Middle Drag")
        menu.addAction("🔍 Zoom In / Out\tMouse Wheel")
        menu.addAction("🗑 Delete Selected\tDelete / Backspace")
        menu.addAction("❌ Cancel / Dismiss\tEscape")

        menu.addSeparator()

        act_editor = menu.addAction("⚙ Open Node Graph Editor...")
        act_editor.triggered.connect(self._on_customize_macro)

        return menu

    def _show_shortcuts_menu(self):
        menu = self._build_shortcuts_menu()
        btn_pos = self.help_btn.mapToGlobal(QPoint(0, self.help_btn.height() + 2))
        menu_width = menu.sizeHint().width()
        x = btn_pos.x() + self.help_btn.width() - menu_width
        y = btn_pos.y()
        menu.exec(QPoint(x, y))

    def _create_footer_bar(self):
        bar = QFrame(self)
        bar.setObjectName("FooterBar")
        bar.setMouseTracking(True)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 1, 2, 1)
        layout.setSpacing(4)

        hint_lbl = QLabel("Stop: Alt+S (or F12)")
        hint_lbl.setObjectName("FooterHint")
        hint_lbl.setToolTip("Press Alt+S or F12 at any time to immediately halt playback")
        layout.addWidget(hint_lbl)

        layout.addStretch()

        grip = QSizeGrip(self)
        grip.setToolTip("Drag here to resize window (or drag any outer border)")
        layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        return bar

    def _create_opacity_section(self):
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        lbl = QLabel("Opacity:")
        lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        row.addWidget(lbl)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(95)
        self.opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        row.addWidget(self.opacity_slider, 1)

        self.opacity_lbl = QLabel("95%")
        self.opacity_lbl.setFixedWidth(32)
        self.opacity_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px; font-family: 'Consolas', monospace;")
        row.addWidget(self.opacity_lbl)

        widget = QWidget()
        widget.setLayout(row)
        return widget

    def _create_macro_recorder_section(self):
        box = QFrame()
        box.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 4px;")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        row = QHBoxLayout()
        self.record_btn = QPushButton("● Record Macro")
        self.record_btn.setObjectName("RecordBtn")
        self.record_btn.clicked.connect(self.toggle_recording)
        row.addWidget(self.record_btn, 1)

        self.record_status_lbl = QLabel("0 steps")
        self.record_status_lbl.setObjectName("StatusBadge")
        row.addWidget(self.record_status_lbl)
        layout.addLayout(row)

        return box

    def _create_macro_playback_section(self):
        box = QFrame()
        box.setStyleSheet("background-color: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 4px;")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Macro selector row
        sel_row = QHBoxLayout()
        self.macro_combo = QComboBox()
        self.macro_combo.setMaxVisibleItems(15)
        self.macro_combo.currentIndexChanged.connect(self._on_selected_macro_changed)
        sel_row.addWidget(self.macro_combo, 1)

        self.del_macro_btn = QPushButton("🗑")
        self.del_macro_btn.setFixedWidth(28)
        self.del_macro_btn.setToolTip("Delete selected macro")
        self.del_macro_btn.clicked.connect(self._on_delete_macro)
        sel_row.addWidget(self.del_macro_btn)

        self.customize_macro_btn = QPushButton("⚙ Customize")
        self.customize_macro_btn.setObjectName("CustomizeBtn")
        self.customize_macro_btn.setToolTip("Open visual Node Graph Editor to customize this macro")
        self.customize_macro_btn.clicked.connect(self._on_customize_macro)
        sel_row.addWidget(self.customize_macro_btn)
        layout.addLayout(sel_row)

        # Controls row: Play, Pause, Stop
        btn_row = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setObjectName("PlayBtn")
        self.play_btn.clicked.connect(self.start_playback)
        btn_row.addWidget(self.play_btn, 1)

        self.pause_btn = QPushButton("⏸ Pause")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self.toggle_pause)
        btn_row.addWidget(self.pause_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("Stop playback (Alt+S)")
        self.stop_btn.clicked.connect(self.stop_playback)
        btn_row.addWidget(self.stop_btn)
        layout.addLayout(btn_row)

        # Speed slider
        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(25, 300)
        self.speed_slider.setValue(100)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_slider, 1)

        self.speed_lbl = QLabel("1.0x")
        self.speed_lbl.setFixedWidth(30)
        self.speed_lbl.setStyleSheet("color: #a1a1aa; font-family: 'Consolas', monospace; font-size: 11px;")
        speed_row.addWidget(self.speed_lbl)
        layout.addLayout(speed_row)

        # Repetition options: Repeat until Stop + Repeat X Times
        repeat_row = QHBoxLayout()
        repeat_row.setSpacing(6)

        self.loop_check = QCheckBox("Repeat until Stop")
        self.loop_check.setToolTip("Loop macro continuously until Stop button or Alt+S is pressed")
        self.loop_check.toggled.connect(self._on_loop_toggled)
        repeat_row.addWidget(self.loop_check)

        repeat_row.addStretch()

        repeat_lbl = QLabel("Repeat:")
        repeat_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        repeat_row.addWidget(repeat_lbl)

        self.repeat_count_spin = QSpinBox()
        self.repeat_count_spin.setRange(1, 99999)
        self.repeat_count_spin.setValue(1)
        self.repeat_count_spin.setMinimumWidth(80)
        self.repeat_count_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.repeat_count_spin.setToolTip("Set custom number of times to repeat this macro")
        self.repeat_count_spin.valueChanged.connect(self._on_repeat_count_changed)
        repeat_row.addWidget(self.repeat_count_spin)

        times_lbl = QLabel("times")
        times_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        repeat_row.addWidget(times_lbl)

        layout.addLayout(repeat_row)

        # Status badge row
        status_row = QHBoxLayout()
        status_lbl = QLabel("Status:")
        status_lbl.setStyleSheet("color: #71717a; font-size: 11px;")
        status_row.addWidget(status_lbl)

        self.status_badge = QLabel("IDLE")
        self.status_badge.setObjectName("StatusBadge")
        status_row.addWidget(self.status_badge)
        status_row.addStretch()
        layout.addLayout(status_row)

        return box

    def _create_export_import_section(self):
        row = QHBoxLayout()
        row.setContentsMargins(2, 0, 2, 0)
        self.import_btn = QPushButton("Import JSON...")
        self.import_btn.clicked.connect(self._on_import_clicked)
        row.addWidget(self.import_btn, 1)

        self.export_btn = QPushButton("Export All...")
        self.export_btn.clicked.connect(self._on_export_clicked)
        row.addWidget(self.export_btn, 1)

        widget = QWidget()
        widget.setLayout(row)
        return widget

    def _restore_settings(self):
        # Restore Opacity
        opacity = self.cfg.get_opacity()
        self.opacity_slider.setValue(int(opacity * 100))
        self.setWindowOpacity(opacity)

        # Restore Macros dropdown
        self._refresh_macros_dropdown()

        # Restore Instance settings
        inst = self.cfg.get_instance_settings(self.instance_id)
        if inst.get("x") is not None and inst.get("y") is not None:
            saved_x = int(inst["x"])
            saved_y = int(inst["y"])
            # Validate that saved coordinates are on a real visible screen
            screens = QGuiApplication.screens()
            visible_on_screen = False
            for s in screens:
                geom = s.availableGeometry()
                if geom.intersects(QRect(saved_x, saved_y, 100, 50)):
                    visible_on_screen = True
                    break
            if visible_on_screen and saved_x > -10000 and saved_y > -10000:
                self.move(saved_x, saved_y)
            else:
                primary = QGuiApplication.primaryScreen()
                if primary:
                    avail = primary.availableGeometry()
                    self.move(
                        avail.x() + (avail.width() - self.width()) // 2,
                        avail.y() + (avail.height() - self.height()) // 2,
                    )

        if inst.get("width") and inst.get("height"):
            screen = QGuiApplication.primaryScreen()
            max_h = screen.availableGeometry().height() - 40 if screen else 900
            max_w = screen.availableGeometry().width() - 40 if screen else 1200
            w = max(280, min(max_w, int(inst["width"])))
            h = max(160, min(max_h, int(inst["height"])))
            self.resize(w, h)
            self._unminimized_height = h

        if inst.get("speed"):
            spd_val = int(inst["speed"] * 100)
            self.speed_slider.setValue(spd_val)
            self.speed_lbl.setText(f"{inst['speed']:.2f}x")

        if inst.get("repeat") is not None:
            self.loop_check.setChecked(bool(inst["repeat"]))

        if inst.get("repeat_count"):
            self.repeat_count_spin.setValue(max(1, int(inst["repeat_count"])))

        if inst.get("selected_macro"):
            idx = self.macro_combo.findText(inst["selected_macro"])
            if idx >= 0:
                self.macro_combo.setCurrentIndex(idx)

        # Always start up in normal visible state, never minimized
        self.showNormal()

    def _update_cursor_readout(self):
        x, y = get_cursor_pos()
        self.coords_pill.setText(f"X: {x}  Y: {y}")

    def _on_opacity_slider_changed(self, val):
        alpha = val / 100.0
        self.opacity_lbl.setText(f"{val}%")
        self.setWindowOpacity(alpha)
        self.cfg.set_opacity(alpha)

    def _refresh_macros_dropdown(self):
        current_selection = self.macro_combo.currentText()
        macros = self.cfg.get_macros()
        self.macro_combo.blockSignals(True)
        self.macro_combo.clear()
        for name in sorted(macros.keys()):
            self.macro_combo.addItem(name)

        if current_selection and current_selection in macros:
            self.macro_combo.setCurrentText(current_selection)
        elif self.macro_combo.count() > 0:
            self.macro_combo.setCurrentIndex(0)
        self.macro_combo.blockSignals(False)

        has_macros = self.macro_combo.count() > 0
        self.play_btn.setEnabled(has_macros and not self.player.is_playing())
        self.del_macro_btn.setEnabled(has_macros)

    # Macro Recorder
    def toggle_recording(self):
        if self.recorder.is_recording:
            steps, duration = self.recorder.stop()
            self.record_btn.setText("● Record Macro")
            self.record_btn.setObjectName("RecordBtn")
            self.record_btn.setStyleSheet("")

            if steps:
                # Apply user's default_direct_move setting
                default_direct = self.cfg.get_editor_setting("default_direct_move", True)
                steps = self._process_recorded_steps(steps, default_direct_move=default_direct)
                duration = steps[-1].get("dt", duration) if steps else duration

                default_name = self.cfg.generate_next_macro_name()
                dlg = MacroNameDialog(default_name, len(steps), duration, self)
                if dlg.exec():
                    macro_name = dlg.get_macro_name()
                    self.cfg.save_macro(macro_name, steps, duration)
                    self._refresh_macros_dropdown()
                    self.macro_combo.setCurrentText(macro_name)
                    QMessageBox.information(
                        self, "Saved", f"Macro '{macro_name}' saved successfully!"
                    )
            self.record_status_lbl.setText("0 steps")
        else:
            self.stop_playback()
            self.recorder.start()
            self.record_btn.setText("■ Stop Recording")
            self.record_btn.setStyleSheet("background-color: #e11d48; color: white; font-weight: bold;")
            self.record_status_lbl.setText("0 steps")

    def _process_recorded_steps(self, steps, default_direct_move=True):
        """Processes recorded macro steps according to default_direct_move preference."""
        if not steps:
            return []

        import copy
        if not default_direct_move:
            processed = []
            for s in steps:
                st = copy.deepcopy(s)
                if st.get("type") == "move":
                    st["direct_jump"] = False
                processed.append(st)
            return processed

        # default_direct_move is True: collapse consecutive move streams into single target move
        compacted = []
        i = 0
        n = len(steps)
        while i < n:
            step = steps[i]
            st_type = step.get("type")
            if st_type == "move":
                path = [step]
                while (i + 1 < n) and steps[i + 1].get("type") == "move":
                    i += 1
                    path.append(steps[i])
                last_m = copy.deepcopy(path[-1])
                last_m["type"] = "move"
                last_m["path_points"] = path
                last_m["direct_jump"] = True
                compacted.append(last_m)
                i += 1
                continue
            compacted.append(step)
            i += 1
        return compacted

    def _on_recorder_step_count(self, count):
        self.record_status_lbl.setText(f"{count} steps")

    def _on_recorder_max_steps(self):
        QMessageBox.warning(
            self, "Limit Reached", "Maximum step limit (6000 steps) reached. Stopping recording."
        )
        self.toggle_recording()

    # Macro Playback
    def start_playback(self):
        name = self.macro_combo.currentText()
        macro = self.cfg.get_macro(name)
        if not macro or not macro.get("steps"):
            return

        steps = macro.get("steps", [])
        speed = self.speed_slider.value() / 100.0
        repeat_infinite = self.loop_check.isChecked()
        repeat_count = self.repeat_count_spin.value()

        # Request cursor access from scheduler
        granted = GLOBAL_SCHEDULER.request_playback(
            self.instance_id,
            lambda: self.player.play(steps, speed, repeat=repeat_infinite, repeat_count=repeat_count)
        )
        if granted:
            self.player.play(steps, speed, repeat=repeat_infinite, repeat_count=repeat_count)

    def toggle_pause(self):
        if self.player.is_paused():
            self.player.resume()
            self.pause_btn.setText("⏸ Pause")
        else:
            self.player.pause()
            self.pause_btn.setText("▶ Resume")

    def stop_playback(self):
        self.player.stop()
        set_window_click_through(self.winId(), False)
        GLOBAL_SCHEDULER.release_playback(self.instance_id)

    def _on_player_state_changed(self, state):
        is_playing = state in (MacroPlayer.STATE_PLAYING, MacroPlayer.STATE_PAUSED)
        self.play_btn.setEnabled(not is_playing)
        self.pause_btn.setEnabled(is_playing)
        self.stop_btn.setEnabled(is_playing)
        self.macro_combo.setEnabled(not is_playing)
        self.del_macro_btn.setEnabled(not is_playing)

        if state == MacroPlayer.STATE_PLAYING:
            self.pause_btn.setText("⏸ Pause")
            # Always hard-coded click-through: clicks pass directly to the underlying app
            set_window_click_through(self.winId(), True)
            self.status_badge.setText("SEE-THROUGH (Alt+S)")
            self.status_badge.setObjectName("StatusBadgeRunning")
        elif state == MacroPlayer.STATE_PAUSED:
            self.status_badge.setText("PAUSED")
            self.status_badge.setObjectName("StatusBadgeWarning")
            self.pause_btn.setText("▶ Resume")
            set_window_click_through(self.winId(), False)
        elif state == MacroPlayer.STATE_IDLE:
            self.status_badge.setText("IDLE")
            self.status_badge.setObjectName("StatusBadge")
            self.indicator.hide_dot()
            GLOBAL_SCHEDULER.release_playback(self.instance_id)
            set_window_click_through(self.winId(), False)

    def _on_pass_progress(self, current, total):
        self._current_pass = current
        self._total_passes = total
        if total > 0:
            self.status_badge.setText(f"Pass {current}/{total}")
        else:
            self.status_badge.setText(f"Looping (Pass {current})")

    def _on_player_progress(self, current_step, total_steps):
        if self._total_passes > 1:
            self.status_badge.setText(f"Pass {self._current_pass}/{self._total_passes} ({current_step}/{total_steps})")
        elif self.loop_check.isChecked():
            self.status_badge.setText(f"Pass {self._current_pass} ({current_step}/{total_steps})")
        else:
            self.status_badge.setText(f"{current_step}/{total_steps}")

    def _on_cursor_action(self, x, y, action_type):
        if action_type in ("click", "dblclick", "down"):
            self.indicator.show_at(x, y, 180)

    def _on_scheduler_status(self, status):
        self.bridges.scheduler_status.emit(status)

    def _update_scheduler_status_ui(self, status):
        if status.startswith("QUEUED"):
            self.status_badge.setText(status)
            self.status_badge.setObjectName("StatusBadgeWarning")
            self.stop_btn.setEnabled(True)

    def _on_speed_changed(self, val):
        spd = val / 100.0
        self.speed_lbl.setText(f"{spd:.2f}x")
        self.cfg.update_instance_settings(self.instance_id, speed=spd)

    def _on_loop_toggled(self, checked):
        self.player.set_repeat(checked)
        self.repeat_count_spin.setEnabled(not checked)
        self.cfg.update_instance_settings(self.instance_id, repeat=checked)

    def _on_repeat_count_changed(self, val):
        self.cfg.update_instance_settings(self.instance_id, repeat_count=int(val))

    def _on_selected_macro_changed(self, idx):
        name = self.macro_combo.currentText()
        if name:
            self.cfg.update_instance_settings(self.instance_id, selected_macro=name)

    def _on_delete_macro(self):
        name = self.macro_combo.currentText()
        if not name:
            return
        reply = QMessageBox.question(
            self, "Delete Macro", f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.cfg.delete_macro(name)
            self._refresh_macros_dropdown()

    def _on_customize_macro(self):
        name = self.macro_combo.currentText()
        if not name:
            QMessageBox.information(
                self, "No Macro Selected", "Please select or record a macro first to customize."
            )
            return

        macro_data = self.cfg.get_macro(name)
        if not macro_data:
            return

        steps = macro_data.get("steps", [])

        if not hasattr(self, "_editor_windows"):
            self._editor_windows = {}

        def on_save_compiled(macro_name, updated_steps, graph_data=None):
            self.cfg.save_macro(macro_name, updated_steps, graph_data=graph_data)
            self._refresh_macros_dropdown()

        editor_win = MacroNodeEditorWindow(
            macro_name=name,
            macro_steps=steps,
            on_save_callback=on_save_compiled,
            config=self.cfg,
            parent=None,
        )
        editor_win.parent_panel = self
        self._editor_windows[name] = editor_win
        editor_win.show()
        editor_win.raise_()
        editor_win.activateWindow()

    # Export & Import
    def _on_export_clicked(self):
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        default_filename = f"macrow-macros-{date_str}.json"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Macros", default_filename, "JSON Files (*.json)"
        )
        if filepath:
            count = self.cfg.export_macros_to_file(filepath)
            QMessageBox.information(
                self, "Export Successful", f"Exported {count} macro(s) to:\n{filepath}"
            )

    def _on_import_clicked(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Macros", "", "JSON Files (*.json)"
        )
        if not filepath:
            return

        wizard = ImportWizardDialog(filepath, self)
        if wizard.exec():
            dx, dy = wizard.get_offsets()
            imported = self.cfg.import_macros_from_file(filepath, dx, dy)
            self._refresh_macros_dropdown()
            msg = f"Successfully imported {len(imported)} macro(s)!\n" + ", ".join(imported[:5])
            if len(imported) > 5:
                msg += f" ...and {len(imported) - 5} more."
            QMessageBox.information(self, "Import Successful", msg)

    # Shared Config Updates
    def _on_shared_config_changed(self, new_data):
        self._refresh_macros_dropdown()

    # Minimize / Restore to Taskbar
    def toggle_minimize(self, force_minimized=None):
        """Minimize or restore the Macrow window to/from the Windows taskbar."""
        if force_minimized is True:
            self.showMinimized()
        elif force_minimized is False:
            self.showNormal()
        else:
            if self.isMinimized():
                self.showNormal()
            else:
                self.showMinimized()

    def changeEvent(self, event):
        super().changeEvent(event)

    # Robust Edge Resizing & Window Dragging via EventFilter
    def _get_resize_mode(self, pos):
        """Determines which edge or corner the cursor is hovering near."""
        w = self.width()
        h = self.height()
        x = pos.x()
        y = pos.y()
        m = self.RESIZE_MARGIN

        on_left = x <= m
        on_right = x >= w - m
        on_top = y <= m
        on_bottom = y >= h - m

        # Title bar area is dedicated to window dragging, not top-edge resize
        if hasattr(self, "title_bar") and y <= self.title_bar.height() + 2:
            if not (on_left or on_right):
                return None

        if on_bottom and on_right:
            return "bottom_right"
        elif on_bottom and on_left:
            return "bottom_left"
        elif on_top and on_right:
            return "top_right"
        elif on_top and on_left:
            return "top_left"
        elif on_right:
            return "right"
        elif on_left:
            return "left"
        elif on_bottom:
            return "bottom"
        elif on_top:
            return "top"
        return None

    def _set_resize_cursor(self, mode):
        if mode in ("bottom_right", "top_left"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif mode in ("bottom_left", "top_right"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif mode in ("left", "right"):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif mode in ("bottom", "top"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def _handle_resize_move(self, cur_global):
        dx = cur_global.x() - self._resize_start_pos.x()
        dy = cur_global.y() - self._resize_start_pos.y()
        orig = self._resize_start_geom

        new_x = orig.x()
        new_y = orig.y()
        new_w = orig.width()
        new_h = orig.height()

        mode = self._is_resizing
        if "right" in mode:
            new_w = max(self.minimumWidth(), orig.width() + dx)
        elif "left" in mode:
            pot_w = orig.width() - dx
            if pot_w >= self.minimumWidth():
                new_w = pot_w
                new_x = orig.x() + dx

        if "bottom" in mode:
            new_h = max(self.minimumHeight(), orig.height() + dy)
        elif "top" in mode:
            pot_h = orig.height() - dy
            if pot_h >= self.minimumHeight():
                new_h = pot_h
                new_y = orig.y() + dy

        self.setGeometry(new_x, new_y, new_w, new_h)
        self._unminimized_height = self.height()

    def _finish_resize(self):
        self._is_resizing = None
        self.cfg.update_instance_settings(
            self.instance_id,
            x=self.x(),
            y=self.y(),
            width=self.width(),
            height=self.height(),
        )
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def eventFilter(self, watched, event):
        """Intercept mouse events on container and scroll viewport for 100% reliable edge resizing."""
        ev_type = event.type()

        # Prioritize active window dragging over child widget events
        if self._is_dragging:
            if ev_type == QEvent.Type.MouseMove:
                global_pos = event.globalPosition().toPoint()
                new_pos = global_pos - self._drag_start_pos
                self.move(new_pos)
                return True
            elif ev_type == QEvent.Type.MouseButtonRelease:
                self._is_dragging = False
                self.cfg.update_instance_settings(self.instance_id, x=self.x(), y=self.y())
                return True

        if ev_type in (QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            global_pos = event.globalPosition().toPoint()
            local_pt = self.mapFromGlobal(global_pos)
            mode = self._get_resize_mode(local_pt)

            if ev_type == QEvent.Type.MouseMove:
                if self._is_resizing:
                    self._handle_resize_move(global_pos)
                    return True
                if mode:
                    self._set_resize_cursor(mode)
                    return True
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

            elif ev_type == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton and mode:
                    self._is_resizing = mode
                    self._resize_start_pos = global_pos
                    self._resize_start_geom = self.geometry()
                    return True

            elif ev_type == QEvent.Type.MouseButtonRelease:
                if self._is_resizing:
                    self._finish_resize()
                    return True

        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()

            # Dragging title bar has priority over edge-resizing
            if pos.y() <= self.title_bar.height() + 4 and not (pos.x() <= self.RESIZE_MARGIN or pos.x() >= self.width() - self.RESIZE_MARGIN):
                self._is_dragging = True
                self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return

            mode = self._get_resize_mode(pos)
            if mode:
                self._is_resizing = mode
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        global_pos = event.globalPosition().toPoint()
        if self._is_resizing:
            self._handle_resize_move(global_pos)
            event.accept()
            return

        if self._is_dragging:
            new_pos = global_pos - self._drag_start_pos
            self.move(new_pos)
            self.cfg.update_instance_settings(self.instance_id, x=new_pos.x(), y=new_pos.y())
            event.accept()
            return

        pos = event.position().toPoint()
        mode = self._get_resize_mode(pos)
        if mode:
            self._set_resize_cursor(mode)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_resizing:
            self._finish_resize()
            event.accept()
            return

        if self._is_dragging:
            self._is_dragging = False
            self.cfg.update_instance_settings(self.instance_id, x=self.x(), y=self.y())
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """Enable smooth mouse wheel scrolling over the entire panel."""
        if not self.scroll_area.isHidden():
            sb = self.scroll_area.verticalScrollBar()
            delta = event.angleDelta().y()
            sb.setValue(sb.value() - int(delta * 0.8))
            event.accept()
        else:
            super().wheelEvent(event)

    def closeEvent(self, event):
        self.stop_playback()
        self.recorder.stop()
        self.indicator.hide_dot()
        GLOBAL_SCHEDULER.unregister_instance(self.instance_id)
        super().closeEvent(event)
        self.deleteLater()


# Backward compatibility alias
PointClickerPanel = MacrowPanel
