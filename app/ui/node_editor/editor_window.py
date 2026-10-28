"""Dedicated top-level window for the Node Graph Editor."""

from __future__ import annotations

import os
from typing import List, Dict, Any, Optional, Callable
from PyQt6.QtCore import Qt, QPointF, QPoint, QTimer
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QSplitter,
    QToolBar,
    QPushButton,
    QMenu,
    QLabel,
    QMessageBox,
    QStatusBar,
    QApplication,
    QDialog,
    QCheckBox,
    QFrame,
)

from app.ui.node_editor.node_scene import NodeScene
from app.ui.node_editor.node_view import NodeView
from app.ui.node_editor.inspector import PropertyInspector
from app.ui.node_editor.graph_compiler import macro_to_graph, graph_to_macro
from app.ui.node_editor.node_items import (
    BaseNodeItem,
    StartNodeItem,
    ActionNodeItem,
    VisionNodeItem,
    IfConditionNodeItem,
    MathNodeItem,
    PixelColorNodeItem,
    HotkeyNodeItem,
    LoopNodeItem,
    StopNodeItem,
)
from app.ui.snippet_tool import ScreenSnipper
from app.ui.node_editor.undo_manager import UndoManager, serialize_scene, deserialize_scene
from app.ui.assets import get_app_icon


class MacroNodeEditorWindow(QMainWindow):
    """Visual left-to-right node flow customizer for macros."""

    def __init__(
        self,
        macro_name: str,
        macro_steps: List[Dict[str, Any]],
        on_save_callback: Optional[Callable[[str, List[Dict[str, Any]]], None]] = None,
        config: Optional[Any] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.macro_name = macro_name
        self.macro_steps = list(macro_steps)
        self.on_save_callback = on_save_callback
        self.config = config
        self._has_unsaved_changes = False

        self.setWindowTitle(f"Macrow - Node Customizer [{macro_name}]")
        self.setWindowIcon(get_app_icon())
        self.resize(1180, 740)
        self.setMinimumSize(850, 500)

        self._init_ui()
        self._load_macro_graph()

    def _init_ui(self):
        # Dark modern styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0f172a;
            }
            QToolBar {
                background-color: #1e293b;
                border-bottom: 1px solid #334155;
                padding: 6px 12px;
                spacing: 8px;
            }
            QPushButton {
                background-color: #334155;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px 12px;
                font-family: 'Segoe UI';
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #475569;
                border-color: #38bdf8;
            }
            QPushButton:pressed {
                background-color: #1e293b;
            }
            QMenu {
                background-color: #1e293b;
                color: #f1f5f9;
                border: 1px solid #475569;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #0284c7;
            }
            QStatusBar {
                background-color: #1e293b;
                color: #94a3b8;
                border-top: 1px solid #334155;
                font-size: 11px;
            }
            QSplitter::handle:horizontal {
                background-color: #334155;
                width: 6px;
            }
            QSplitter::handle:horizontal:hover {
                background-color: #38bdf8;
            }
            QSplitter::handle:horizontal:pressed {
                background-color: #0284c7;
            }
        """)

        # Toolbar
        toolbar = QToolBar("Editor Actions", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Add Node Button with Dropdown Menu
        self.add_node_btn = QPushButton("➕ Add Node ▾")
        add_menu = QMenu(self)
        
        # Mouse Actions
        add_menu.addAction("🖱 Mouse Click", lambda: self._add_action_node("click"))
        add_menu.addAction("🖱 Double Click", lambda: self._add_action_node("dblclick"))
        add_menu.addAction("🏹 Mouse Move", lambda: self._add_action_node("move"))
        add_menu.addAction("📜 Mouse Wheel Scroll", lambda: self._add_action_node("wheel"))
        add_menu.addAction("⏳ Delay / Wait", lambda: self._add_action_node("delay"))
        add_menu.addAction("🔤 Type Text", lambda: self._add_action_node("type"))
        add_menu.addAction("⌨ Key Combo (Hotkey)", lambda: self._add_custom_node(HotkeyNodeItem()))
        add_menu.addSeparator()

        # Logic & Conditions
        add_menu.addAction("🔀 If / Compare Condition", lambda: self._add_custom_node(IfConditionNodeItem()))
        add_menu.addAction("🎨 Pixel Color Check", lambda: self._add_custom_node(PixelColorNodeItem()))
        add_menu.addAction("🔁 Loop (N Times)", lambda: self._add_custom_node(LoopNodeItem()))
        add_menu.addSeparator()

        # Math & Variables
        add_menu.addAction("🔢 Math / Variable", lambda: self._add_custom_node(MathNodeItem()))
        add_menu.addSeparator()

        # Vision AI
        add_menu.addAction("⏱ Wait For Image (AI Screen)", lambda: self._add_vision_node("wait_image"))
        add_menu.addSeparator()

        # Control Flow
        add_menu.addAction("⏹ Stop Playback", lambda: self._add_custom_node(StopNodeItem()))

        self.add_node_btn.setMenu(add_menu)
        toolbar.addWidget(self.add_node_btn)

        # Quick Snippet Button
        self.snip_btn = QPushButton("📸 Snip")
        self.snip_btn.setToolTip("Snip image from screen for visual recognition")
        self.snip_btn.clicked.connect(self._quick_snip)
        toolbar.addWidget(self.snip_btn)

        # Examples / Presets Dropdown
        self.examples_btn = QPushButton("📚 Examples ▾")
        self.examples_btn.setToolTip("Load working example node setups to test and explore")
        ex_menu = QMenu(self)
        ex_menu.addAction("🔁 1. Auto-Clicker Loop (5x with Delay)", lambda: self._load_example_preset("auto_clicker"))
        ex_menu.addAction("🎯 2. Loop Until Image Found (Breakout)", lambda: self._load_example_preset("loop_until_image"))
        ex_menu.addAction("🔢 3. Coordinate Step with Math ($y = $y + 50)", lambda: self._load_example_preset("math_grid"))
        ex_menu.addAction("🎨 4. Pixel Color Polling (Wait until Green)", lambda: self._load_example_preset("pixel_polling"))
        self.examples_btn.setMenu(ex_menu)
        toolbar.addWidget(self.examples_btn)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QWidget().sizePolicy().Policy.Expanding, QWidget().sizePolicy().Policy.Preferred)
        toolbar.addWidget(spacer)

        # Fit all view button
        self.reset_view_btn = QPushButton("🔍 Fit All")
        self.reset_view_btn.setToolTip("Frames the entire node graph into view")
        self.reset_view_btn.clicked.connect(self._reset_view)
        toolbar.addWidget(self.reset_view_btn)

        # Settings Gear button
        self.settings_btn = QPushButton("⚙ Settings")
        self.settings_btn.setToolTip("Configure Node Editor preferences and defaults")
        self.settings_btn.clicked.connect(self._open_settings_dialog)
        toolbar.addWidget(self.settings_btn)

        # Shortcuts Help button
        self.help_btn = QPushButton("? Shortcuts")
        self.help_btn.setToolTip("View all keyboard shortcuts and gestures")
        self.help_btn.clicked.connect(self._show_shortcuts_menu)
        toolbar.addWidget(self.help_btn)

        # Save & Apply button - with pressed animation matching settings and fit all
        self.save_btn = QPushButton("💾 Save & Apply")
        self.save_btn.setToolTip("Save & apply macro changes (Ctrl+S)")
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: #ffffff;
                font-weight: bold;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 6px 14px;
                min-width: 95px;
            }
            QPushButton:hover {
                background-color: #0369a1;
                border-color: #7dd3fc;
            }
            QPushButton:pressed {
                background-color: #075985;
                border-color: #0284c7;
                padding-top: 8px;
                padding-bottom: 4px;
                padding-left: 15px;
                padding-right: 13px;
            }
        """)
        self.save_btn.clicked.connect(lambda: self._save_and_apply(show_notification=True))
        toolbar.addWidget(self.save_btn)

        # Central Layout: QSplitter with horizontal draggable handle between View and Inspector!
        self.scene = NodeScene(self)
        self.view = NodeView(self.scene, self)
        self.inspector = PropertyInspector(self.scene, self)

        # Undo / Redo Manager
        self.undo_manager = UndoManager(self.scene, parent=self)
        self.undo_manager.state_changed.connect(self._update_undo_redo_ui)

        # Track changes to prompt save on close and record undo history
        self.scene.scene_modified.connect(self._mark_changed)
        self.inspector.property_changed.connect(self._mark_changed)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.inspector)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([850, 310])

        self.setCentralWidget(self.splitter)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select and drag nodes to customize execution flow.")

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+S"), self, self._save_and_apply)
        QShortcut(QKeySequence("Ctrl+Z"), self, self._on_undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self._on_redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self._on_redo)
        QShortcut(QKeySequence("Ctrl+C"), self, self._copy_selected)
        QShortcut(QKeySequence("Ctrl+V"), self, self._paste_selected)
        QShortcut(QKeySequence("Ctrl+A"), self, self._select_all_nodes)
        QShortcut(QKeySequence("Ctrl+D"), self, self._duplicate_selected)
        QShortcut(QKeySequence("Ctrl+G"), self, self._group_selected)
        QShortcut(QKeySequence("R"), self, self.view.frame_selected)
        QShortcut(QKeySequence("B"), self, self._toggle_bypass_selected)
        QShortcut(QKeySequence("Delete"), self, self._delete_selected)

    def _toggle_bypass_selected(self):
        count = self.scene.toggle_bypass_selected()
        if count > 0:
            self._has_unsaved_changes = True
            self.status_bar.showMessage(f"Toggled bypass on {count} node(s) (B).")
            if self.inspector.current_node:
                self.inspector.set_node(self.inspector.current_node)
        else:
            self.status_bar.showMessage("Select node(s) to bypass or unbypass (B).")

    def _show_shortcuts_menu(self):
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

        menu.addSection("NODE GRAPH EDITOR SHORTCUTS")
        menu.addAction("⚡ Quick Add Node\tTab")
        menu.addAction("🎯 Center / Frame View\tR")
        menu.addAction("☑ Select All Nodes\tCtrl+A")
        menu.addAction("🚫 Bypass / Mute Node(s)\tB")
        menu.addAction("↔ Align Branch (R/L)\tA + Drag")
        menu.addAction("➡ Move Branch Right\tCtrl + Drag")
        menu.addAction("⬅ Move Branch Left\tShift + Drag")
        menu.addAction("💥 Shake to Disconnect\tShake Left/Right")
        menu.addAction("🔗 Auto-Insert Node\tDrop onto Wire")
        menu.addAction("💾 Save & Apply\tCtrl+S")
        menu.addAction("↩ Undo Canvas\tCtrl+Z")
        menu.addAction("↪ Redo Canvas\tCtrl+Y")
        menu.addAction("📋 Copy Nodes\tCtrl+C")
        menu.addAction("📄 Paste Nodes\tCtrl+V")
        menu.addAction("⚡ Duplicate Drag\tAlt + Drag")
        menu.addAction("✂ Cut Wire (Knife)\tY + Drag")
        menu.addAction("🔌 Unplug Wire\tClick Input Socket")
        menu.addAction("✋ Pan Canvas\tRight / Middle Drag")
        menu.addAction("🔍 Zoom In / Out\tMouse Wheel")
        menu.addAction("🗑 Delete Selected (Auto-Heal)\tDelete / Backspace")
        menu.addAction("❌ Cancel / Dismiss\tEscape")

        menu.addSeparator()
        menu.addSection("GLOBAL SHORTCUTS")
        menu.addAction("● Record Macro (Start / Stop)\tF9 / Ctrl+F9")
        menu.addAction("▶ Play / Pause Macro\tF8 / Ctrl+F8")
        menu.addAction("⏹ Stop Playback\tF7 / Ctrl+F7")
        menu.addAction("🛑 Emergency Stop\tAlt+S / F12")

        btn_pos = self.help_btn.mapToGlobal(QPoint(0, self.help_btn.height() + 2))
        menu_width = menu.sizeHint().width()
        x = btn_pos.x() + self.help_btn.width() - menu_width
        y = btn_pos.y()
        menu.exec(QPoint(x, y))

    def _select_all_nodes(self):
        for node in self.scene.nodes:
            node.setSelected(True)
        self.status_bar.showMessage(f"Selected all {len(self.scene.nodes)} node(s) (Ctrl+A).")

    def _copy_selected(self):
        count = self.scene.copy_selected()
        if count > 0:
            self.status_bar.showMessage(f"Copied {count} node(s) to clipboard (Ctrl+C).")
        else:
            self.status_bar.showMessage("Select node(s) to copy.")

    def _paste_selected(self):
        pasted = self.scene.paste_clipboard()
        if pasted:
            self._has_unsaved_changes = True
            self.status_bar.showMessage(f"Pasted {len(pasted)} node(s) (Ctrl+V).")
            self._sync_inspector_after_state_restore()
        else:
            self.status_bar.showMessage("Clipboard is empty.")

    def _mark_changed(self):
        self._has_unsaved_changes = True
        self.undo_manager.push_state()

    def _load_macro_graph(self):
        default_direct = True
        if self.config:
            default_direct = self.config.get_editor_setting("default_direct_move", True)
            macro_obj = self.config.get_macro(self.macro_name)
            if macro_obj and isinstance(macro_obj, dict) and macro_obj.get("graph_data"):
                deserialize_scene(self.scene, macro_obj["graph_data"])
                self.undo_manager.push_state()
                self._has_unsaved_changes = False
                self._update_undo_redo_ui()
                self.view.reset_view()
                count = len(self.scene.nodes)
                self.status_bar.showMessage(f"Loaded {count} custom graph nodes for '{self.macro_name}'.")
                return

        macro_to_graph(self.macro_steps, self.scene, default_direct_move=default_direct)
        self.undo_manager.push_state()
        self._has_unsaved_changes = False
        self._update_undo_redo_ui()
        self.view.reset_view()
        count = len(self.scene.nodes)
        self.status_bar.showMessage(f"Loaded {count} nodes for macro '{self.macro_name}'.")

    def _on_undo(self):
        if self.undo_manager.undo():
            self._has_unsaved_changes = True
            self._sync_inspector_after_state_restore()
            self.status_bar.showMessage("Undone last change (Ctrl+Z).")
        else:
            self.status_bar.showMessage("Nothing to undo.")

    def _on_redo(self):
        if self.undo_manager.redo():
            self._has_unsaved_changes = True
            self._sync_inspector_after_state_restore()
            self.status_bar.showMessage("Redone change (Ctrl+Y).")
        else:
            self.status_bar.showMessage("Nothing to redo.")

    def _sync_inspector_after_state_restore(self):
        sel = self.scene.selectedItems()
        node = next((n for n in sel if isinstance(n, BaseNodeItem)), None)
        self.inspector.set_node(node)

    def _update_undo_redo_ui(self):
        if hasattr(self, "undo_btn"):
            self.undo_btn.setEnabled(self.undo_manager.can_undo())
        if hasattr(self, "redo_btn"):
            self.redo_btn.setEnabled(self.undo_manager.can_redo())

    def _add_action_node(self, action_type: str):
        # Position new node near center of view
        center = self.view.mapToScene(self.view.viewport().rect().center())
        props = {}
        if action_type == "move":
            default_direct = True
            if self.config:
                default_direct = self.config.get_editor_setting("default_direct_move", True)
            props["direct_jump"] = default_direct
        node = ActionNodeItem(action_type=action_type, properties=props)
        self.scene.add_node(node, center)
        self.scene.clearSelection()
        node.setSelected(True)
        self.status_bar.showMessage(f"Added {node.title} node.")

    def _add_vision_node(self, vision_type: str):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        node = VisionNodeItem(vision_type=vision_type)
        self.scene.add_node(node, center)
        self.scene.clearSelection()
        node.setSelected(True)
        self.status_bar.showMessage(f"Added {node.title} node.")

    def _add_custom_node(self, node: BaseNodeItem):
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.scene.add_node(node, center)
        self.scene.clearSelection()
        node.setSelected(True)
        self.status_bar.showMessage(f"Added {node.title} node.")

    def _load_example_preset(self, preset_key: str, confirm: bool = True):
        """Loads a fully wired working example graph illustrating repeat zone and other node patterns."""
        if confirm:
            reply = QMessageBox.question(
                self,
                "Load Example Preset?",
                "Loading this example will populate your node graph with a working setup. Would you like to proceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.scene.clear()
        self.scene.nodes.clear()
        self.scene.connections.clear()
        self.scene.groups.clear()

        start = StartNodeItem()
        self.scene.add_node(start, QPointF(50, 150))

        if preset_key == "auto_clicker":
            # Example 1: Simple Repeat Zone (5x) auto-clicker
            loop = LoopNodeItem(properties={"count": 5, "infinite": False, "var_name": "i"})
            self.scene.add_node(loop, QPointF(280, 120))

            click = ActionNodeItem("click", {"x": 500, "y": 300, "button": "left"})
            self.scene.add_node(click, QPointF(400, 180))

            delay = ActionNodeItem("delay", {"duration": 250})
            self.scene.add_node(delay, QPointF(640, 180))

            stop = StopNodeItem()
            self.scene.add_node(stop, QPointF(920, 320))

            self.scene.add_connection(start.output_sockets[0], loop.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[0], click.input_sockets[0])
            self.scene.add_connection(click.output_sockets[0], delay.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[1], stop.input_sockets[0])

        elif preset_key == "loop_until_image":
            # Example 2: Loop Until Image Found (Breakout)
            loop = LoopNodeItem(properties={"count": 10, "infinite": True, "var_name": "i"})
            self.scene.add_node(loop, QPointF(280, 120))

            scroll = ActionNodeItem("wheel", {"deltaY": -300})
            self.scene.add_node(scroll, QPointF(400, 180))

            delay = ActionNodeItem("delay", {"duration": 500})
            self.scene.add_node(delay, QPointF(640, 180))

            vision = VisionNodeItem("wait_image", {"template": "", "confidence": 0.85, "timeout": 1.0, "break_loop_on_found": True})
            self.scene.add_node(vision, QPointF(880, 180))

            click_found = ActionNodeItem("click", {"x": 960, "y": 540, "button": "left"})
            self.scene.add_node(click_found, QPointF(1180, 340))

            self.scene.add_connection(start.output_sockets[0], loop.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[0], scroll.input_sockets[0])
            self.scene.add_connection(scroll.output_sockets[0], delay.input_sockets[0])
            self.scene.add_connection(delay.output_sockets[0], vision.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[1], click_found.input_sockets[0])

        elif preset_key == "math_grid":
            # Example 3: Loop with Math ($y coordinate increment)
            init_math = MathNodeItem(properties={"var_name": "y", "op": "set", "val_a": "200"})
            self.scene.add_node(init_math, QPointF(250, 150))

            loop = LoopNodeItem(properties={"count": 4, "infinite": False, "var_name": "row"})
            self.scene.add_node(loop, QPointF(480, 120))

            click = ActionNodeItem("click", {"x": 500, "y": "$y", "button": "left"})
            self.scene.add_node(click, QPointF(600, 180))

            delay = ActionNodeItem("delay", {"duration": 200})
            self.scene.add_node(delay, QPointF(840, 180))

            step_math = MathNodeItem(properties={"var_name": "y", "op": "+", "val_a": "$y", "val_b": "60"})
            self.scene.add_node(step_math, QPointF(1080, 180))

            stop = StopNodeItem()
            self.scene.add_node(stop, QPointF(1340, 340))

            self.scene.add_connection(start.output_sockets[0], init_math.input_sockets[0])
            self.scene.add_connection(init_math.output_sockets[0], loop.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[0], click.input_sockets[0])
            self.scene.add_connection(click.output_sockets[0], delay.input_sockets[0])
            self.scene.add_connection(delay.output_sockets[0], step_math.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[1], stop.input_sockets[0])

        elif preset_key == "pixel_polling":
            # Example 4: Loop with Pixel Color Check (Poll until green)
            loop = LoopNodeItem(properties={"count": 100, "infinite": True, "var_name": "attempt"})
            self.scene.add_node(loop, QPointF(280, 120))

            pix_chk = PixelColorNodeItem(properties={"x": 500, "y": 300, "color": "#10B981", "tolerance": 15})
            self.scene.add_node(pix_chk, QPointF(400, 180))

            delay_retry = ActionNodeItem("delay", {"duration": 500})
            self.scene.add_node(delay_retry, QPointF(660, 260))

            click_done = ActionNodeItem("click", {"x": 500, "y": 300, "button": "left"})
            self.scene.add_node(click_done, QPointF(920, 340))

            self.scene.add_connection(start.output_sockets[0], loop.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[0], pix_chk.input_sockets[0])
            # Match (socket 0) connects to post-loop action
            self.scene.add_connection(pix_chk.output_sockets[0], click_done.input_sockets[0])
            # Mismatch (socket 1) loops through delay_retry
            self.scene.add_connection(pix_chk.output_sockets[1], delay_retry.input_sockets[0])
            self.scene.add_connection(loop.output_sockets[1], click_done.input_sockets[0])

        self.scene.update_loop_bounds()
        self.undo_manager.push_state()
        self._has_unsaved_changes = True
        self._update_undo_redo_ui()
        self.view.reset_view()
        self.status_bar.showMessage(f"Loaded example preset '{preset_key}'. Ready to inspect and run.")

    def _quick_eye_dropper(self):
        self.showMinimized()
        from app.ui.eye_dropper import CoordinateEyeDropper
        dropper = CoordinateEyeDropper(parent=None)

        def on_picked(x, y, hex_col, rgb):
            self.showNormal()
            self.activateWindow()
            sel = self.scene.selectedItems()
            target = next((item for item in sel if isinstance(item, (ActionNodeItem, PixelColorNodeItem))), None)
            if target:
                target.properties["x"] = x
                target.properties["y"] = y
                if isinstance(target, PixelColorNodeItem):
                    target.properties["color"] = hex_col
                target.update()
                self.inspector.set_node(target)
                self.status_bar.showMessage(f"Sampled ({x}, {y}) {hex_col} into {target.title}.")
            else:
                node = ActionNodeItem("click", {"x": x, "y": y, "button": "left"})
                center = self.view.mapToScene(self.view.viewport().rect().center())
                self.scene.add_node(node, center)
                self.scene.clearSelection()
                node.setSelected(True)
                self.status_bar.showMessage(f"Created Click node at ({x}, {y}).")

        dropper.coord_picked.connect(on_picked)
        dropper.rejected.connect(lambda: (self.showNormal(), self.activateWindow()))
        dropper.exec()

    def _group_selected(self):
        grp = self.scene.group_selected()
        if grp:
            self.status_bar.showMessage(f"Created group '{grp.title}' with {len(grp.nodes)} nodes.")
        else:
            self.status_bar.showMessage("Select 1 or more nodes to group together.")

    def _duplicate_selected(self):
        dups = self.scene.duplicate_selected()
        if dups:
            self.status_bar.showMessage(f"Duplicated {len(dups)} nodes.")
        else:
            self.status_bar.showMessage("Select nodes to duplicate.")

    def _delete_selected(self):
        self.scene.delete_selected()
        self.status_bar.showMessage("Deleted selected items.")

    def _quick_snip(self):
        self.showMinimized()
        snipper = ScreenSnipper(parent=None)

        def on_snip_done(qimg, filepath):
            self.showNormal()
            self.activateWindow()
            # If a vision node is selected, assign snippet to it!
            sel = self.scene.selectedItems()
            v_node = next((item for item in sel if isinstance(item, VisionNodeItem)), None)
            if v_node:
                v_node.update_template(filepath)
                self.inspector.set_node(v_node)
                self.status_bar.showMessage(f"Assigned snippet to node '{v_node.title}'.")
            else:
                # Add a new Vision Node with this template
                center = self.view.mapToScene(self.view.viewport().rect().center())
                node = VisionNodeItem("wait_image", properties={"template": filepath, "timeout": 5.0})
                self.scene.add_node(node, center)
                self.scene.clearSelection()
                node.setSelected(True)
                self.status_bar.showMessage("Created new Wait For Image node from snippet.")

        snipper.snippet_captured.connect(on_snip_done)
        snipper.rejected.connect(lambda: (self.showNormal(), self.activateWindow()))
        snipper.exec()

    def _reset_view(self):
        self.view.reset_view()

    def _save_and_apply(self, show_notification: bool = True):
        compiled = graph_to_macro(self.scene)
        graph_data = serialize_scene(self.scene)
        if self.on_save_callback:
            try:
                self.on_save_callback(self.macro_name, compiled, graph_data=graph_data)
            except TypeError:
                self.on_save_callback(self.macro_name, compiled)

        self._has_unsaved_changes = False
        self.status_bar.showMessage(f"✓ Saved {len(compiled)} steps back to macro '{self.macro_name}'!")
        if hasattr(self, "save_btn"):
            self.save_btn.setText("✓ Saved!")
            QTimer.singleShot(1200, lambda: self.save_btn.setText("💾 Save & Apply") if hasattr(self, "save_btn") else None)
        if show_notification:
            QMessageBox.information(
                self,
                "Saved & Applied",
                f"Successfully updated macro '{self.macro_name}' with {len(compiled)} steps.\nReady to play back!",
            )

    def _open_settings_dialog(self):
        """Open settings dialog for configuring node editor defaults and behavior."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Node Editor Settings")
        dialog.setFixedWidth(440)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #0f172a;
                color: #f1f5f9;
            }
            QLabel {
                color: #e2e8f0;
            }
            QCheckBox {
                color: #f1f5f9;
                font-size: 12px;
                font-weight: 500;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #475569;
                background: #1e293b;
            }
            QCheckBox::indicator:checked {
                background-color: #0284c7;
                border-color: #38bdf8;
            }
            QPushButton {
                background-color: #334155;
                color: #f1f5f9;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QLabel("⚙ Editor Configuration")
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        header.setStyleSheet("color: #38bdf8;")
        layout.addWidget(header)

        # Move node default behavior
        box = QFrame()
        box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 12px;")
        box_layout = QVBoxLayout(box)
        box_layout.setSpacing(8)

        lbl_section = QLabel("Mouse Movement Preferences")
        lbl_section.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_section.setStyleSheet("color: #e2e8f0;")
        box_layout.addWidget(lbl_section)

        curr_default = True
        if self.config:
            curr_default = self.config.get_editor_setting("default_direct_move", True)

        chk_default_direct = QCheckBox("Default 'Direct Jump' for Mouse Move nodes")
        chk_default_direct.setChecked(curr_default)
        box_layout.addWidget(chk_default_direct)

        desc = QLabel(
            "• Checked: Recorded mouse moves default to direct jump (skipping intermediate trajectory points).\n"
            "• Unchecked: All recorded intermediate mouse movements are preserved and replayed smoothly."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #94a3b8; font-size: 11px; line-height: 1.4;")
        box_layout.addWidget(desc)

        layout.addWidget(box)

        # Button: Apply setting to all Move nodes currently in the graph
        btn_apply_current = QPushButton("Apply to All Move Nodes Currently in Graph")
        btn_apply_current.setStyleSheet("""
            QPushButton {
                background-color: #1e293b;
                border: 1px solid #475569;
                color: #38bdf8;
                padding: 7px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #334155;
            }
        """)

        def apply_to_existing():
            target_val = chk_default_direct.isChecked()
            changed_count = 0
            for node in self.scene.nodes:
                if isinstance(node, ActionNodeItem) and node.properties.get("action_type", node.node_type) == "move":
                    node.properties["direct_jump"] = target_val
                    node.update()
                    changed_count += 1
            if self.inspector.current_node:
                self.inspector.set_node(self.inspector.current_node)
            self.status_bar.showMessage(f"Updated {changed_count} Move node(s) to Direct Jump = {target_val}.")

        btn_apply_current.clicked.connect(apply_to_existing)
        layout.addWidget(btn_apply_current)

        # Dialog buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("Save Settings")
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #0284c7;
                color: white;
                font-weight: bold;
                border: 1px solid #38bdf8;
            }
            QPushButton:hover {
                background-color: #0369a1;
            }
        """)

        def save_and_close():
            val = chk_default_direct.isChecked()
            if self.config:
                self.config.set_editor_setting("default_direct_move", val)
            self.status_bar.showMessage(f"Settings saved: Default Direct Move = {val}")
            dialog.accept()

        btn_save.clicked.connect(save_and_close)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)
        dialog.exec()

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(60, self.view.fit_all)

    def closeEvent(self, event):
        if self._has_unsaved_changes and os.environ.get("MACROW_TEST_MODE") != "1":
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Save Confirmation")
            dlg.setText(f"Do you want to save changes to macro '{self.macro_name}' before closing?")
            dlg.setIcon(QMessageBox.Icon.Question)
            dlg.setStyleSheet("""
                QMessageBox {
                    background-color: #0f172a;
                    color: #f1f5f9;
                }
                QLabel {
                    color: #e2e8f0;
                    font-size: 12px;
                }
                QPushButton {
                    background-color: #334155;
                    color: #f1f5f9;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 6px 14px;
                    font-weight: 500;
                    min-width: 70px;
                }
                QPushButton:hover {
                    background-color: #475569;
                }
            """)
            btn_save = dlg.addButton("Save & Close", QMessageBox.ButtonRole.AcceptRole)
            btn_save.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: white;
                    font-weight: bold;
                    border: 1px solid #38bdf8;
                    padding: 6px 14px;
                    min-width: 90px;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                }
            """)
            btn_discard = dlg.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = dlg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            dlg.setDefaultButton(btn_save)

            dlg.exec()

            clicked = dlg.clickedButton()
            if clicked == btn_save:
                self._save_and_apply(show_notification=False)
                event.accept()
            elif clicked == btn_discard:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

        if event.isAccepted() and hasattr(self, "parent_panel") and self.parent_panel:
            try:
                if self.parent_panel.isMinimized():
                    self.parent_panel.showNormal()
                self.parent_panel.activateWindow()
                self.parent_panel.raise_()
            except Exception:
                pass
