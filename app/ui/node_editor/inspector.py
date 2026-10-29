"""Property inspector side panel for the node editor."""

from __future__ import annotations

import os
from typing import Optional, TYPE_CHECKING, List, Tuple, Any, Callable
from PyQt6.QtCore import Qt, pyqtSignal, QPoint
from PyQt6.QtGui import QPixmap, QFont, QColor
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QSlider,
    QCheckBox,
    QPushButton,
    QFileDialog,
    QColorDialog,
    QFrame,
    QScrollArea,
    QInputDialog,
    QMenu,
)

from app.ui.node_editor.node_items import (
    BaseNodeItem,
    ActionNodeItem,
    VisionNodeItem,
    IfConditionNodeItem,
    MathNodeItem,
    PixelColorNodeItem,
    HotkeyNodeItem,
    LoopNodeItem,
    StopNodeItem,
)
from app.core.key_catalog import KEY_CATALOG_GROUPS, get_name_for_vk, get_vk_for_key
from app.ui.snippet_tool import ScreenSnipper
from app.ui.eye_dropper import CoordinateEyeDropper

if TYPE_CHECKING:
    from app.ui.node_editor.node_scene import NodeScene


class PropertyInspector(QWidget):
    """Right-side dock panel allowing live editing of selected node properties."""

    property_changed = pyqtSignal()

    def __init__(self, scene: NodeScene, parent=None):
        super().__init__(parent)
        self.node_scene = scene
        self.scene = scene
        self.current_node: Optional[BaseNodeItem] = None

        # Allow flexible resizing from right to left via QSplitter
        self.setMinimumWidth(260)
        self.setMaximumWidth(800)

        self._init_ui()

        # Connect scene selection change
        self.node_scene.node_selected.connect(self.set_node)

    def _init_ui(self):
        self.setStyleSheet("""
            QSpinBox, QDoubleSpinBox {
                background-color: #1e293b;
                color: #ffffff;
                border: 1px solid #475569;
                border-radius: 4px;
                padding-left: 8px;
                padding-right: 28px;
                padding-top: 3px;
                padding-bottom: 3px;
                min-height: 24px;
                font-size: 12px;
                font-weight: 600;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #38bdf8;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 22px;
                height: 12px;
                border-left: 1px solid #475569;
                border-bottom: 1px solid #334155;
                background-color: #334155;
                border-top-right-radius: 3px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
                background-color: #0284c7;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 22px;
                height: 12px;
                border-left: 1px solid #475569;
                background-color: #334155;
                border-bottom-right-radius: 3px;
            }
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #0284c7;
            }
            QLineEdit {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 4px 8px;
                min-height: 22px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
            QComboBox {
                background-color: #1e293b;
                color: #f8fafc;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 4px 28px 4px 8px;
                min-height: 22px;
            }
            QComboBox:focus {
                border: 1px solid #38bdf8;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid #475569;
                border-top-right-radius: 4px;
                border-bottom-right-radius: 4px;
                background-color: #334155;
            }
            QComboBox::drop-down:hover {
                background-color: #0284c7;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #f8fafc;
                width: 0;
                height: 0;
            }
            QComboBox QAbstractItemView {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                selection-background-color: #6366f1;
                selection-color: #ffffff;
                outline: none;
                padding: 4px;
                min-width: 150px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 22px;
                padding: 4px 8px;
                border-radius: 3px;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #6366f1;
                color: #ffffff;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        # Title Header
        header = QLabel("⚙ Property Inspector")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header.setStyleSheet("color: #38bdf8;")
        main_layout.addWidget(header)

        # Scrollable container for dynamic controls
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        self.scroll.setWidget(self.content_widget)

        main_layout.addWidget(self.scroll, 1)

        self._show_empty_state()

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_empty_state(self):
        self._clear_content()
        lbl = QLabel("Select a node on the canvas\nto view and edit its settings.")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #64748b; font-size: 11px; padding: 30px 10px;")
        lbl.setWordWrap(True)
        self.content_layout.addWidget(lbl)
        self.content_layout.addStretch()

    def set_node(self, node: Optional[BaseNodeItem], force: bool = False):
        if node is self.current_node and not force and self.content_layout.count() > 1:
            return
        self.current_node = node
        if not node:
            self._show_empty_state()
            return

        self._clear_content()

        # Node Title Badge
        badge_text = f"Node: {node.title}" + (" [BYPASSED]" if getattr(node, "bypassed", False) else "")
        badge = QLabel(badge_text)
        badge.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        badge.setStyleSheet("color: #f1f5f9; background: #1e293b; padding: 6px; border-radius: 4px;")
        self.content_layout.addWidget(badge)

        # Bypass Checkbox (for any node other than Start)
        from app.ui.node_editor.node_items import StartNodeItem
        if not isinstance(node, StartNodeItem):
            chk_bypass = QCheckBox("🚫 Bypass Node (Skip during playback) [B]")
            chk_bypass.setObjectName("BypassCheckbox")
            chk_bypass.setChecked(getattr(node, "bypassed", False))
            chk_bypass.setStyleSheet("""
                QCheckBox {
                    color: #f59e0b;
                    font-weight: 600;
                    font-size: 11px;
                    padding: 3px 2px;
                }
            """)

            def on_bypass_toggle(checked):
                node.set_bypassed(checked)
                badge.setText(f"Node: {node.title}" + (" [BYPASSED]" if checked else ""))
                self.property_changed.emit()

            chk_bypass.toggled.connect(on_bypass_toggle)
            self.content_layout.addWidget(chk_bypass)

        # Build controls based on node type
        if isinstance(node, VisionNodeItem):
            self._build_vision_controls(node)
        elif isinstance(node, IfConditionNodeItem):
            self._build_if_controls(node)
        elif isinstance(node, MathNodeItem):
            self._build_math_controls(node)
        elif isinstance(node, PixelColorNodeItem):
            self._build_pixel_color_controls(node)
        elif isinstance(node, HotkeyNodeItem):
            self._build_hotkey_controls(node)
        elif isinstance(node, LoopNodeItem):
            self._build_loop_controls(node)
        elif isinstance(node, StopNodeItem):
            self._build_stop_controls(node)
        elif isinstance(node, ActionNodeItem):
            self._build_action_controls(node)
        else:
            info = QLabel(node.get_summary_text() or "No editable settings")
            info.setStyleSheet("color: #94a3b8; font-size: 11px;")
            self.content_layout.addWidget(info)

        self.content_layout.addStretch()

    def _get_known_variables(self) -> List[str]:
        vars_set = {"$i", "$x", "$y", "$pixel_match", "$last_condition"}
        sc = getattr(self, "node_scene", None) or getattr(self, "scene", None)
        if sc:
            if hasattr(sc, "custom_variables") and sc.custom_variables:
                for cv in sc.custom_variables:
                    if cv:
                        vars_set.add(f"${cv.lstrip('$')}")
            if hasattr(sc, "nodes"):
                for n in sc.nodes:
                    if isinstance(n, LoopNodeItem):
                        vn = str(n.properties.get("var_name", "i")).strip()
                        if vn:
                            vars_set.add(f"${vn.lstrip('$')}")
                    elif isinstance(n, MathNodeItem):
                        vn = str(n.properties.get("var_name", "")).strip()
                        if vn:
                            vars_set.add(f"${vn.lstrip('$')}")
                    # Also scan every property value in any node for variables ($var)
                    if hasattr(n, "properties") and isinstance(n.properties, dict):
                        for val in n.properties.values():
                            if isinstance(val, str) and val.strip().startswith("$"):
                                clean_v = val.strip().split(" ")[0].split("+")[0].split("-")[0].strip()
                                if clean_v.startswith("$"):
                                    vars_set.add(clean_v)
        return sorted(list(vars_set))

    def _create_param_input(
        self,
        current_val: Any,
        on_change_callback: Callable[[Any], None],
        placeholder: str = "0 or $var",
        tooltip: str = "Enter a number or variable (e.g. $y, $i)",
        default_type: str = "int",
    ) -> Tuple[QWidget, QLineEdit]:
        """Creates a hybrid parameter input that defaults to 'int' data type,
        with quick mouse-wheel scrolling, dynamic syntax badge, and a comprehensive
        Data Type & Variable selection dropdown.
        """
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        init_str = str(current_val if current_val is not None else "")
        edit = QLineEdit(init_str)
        edit.setPlaceholderText(placeholder)
        edit.setToolTip(tooltip)

        btn_type = QPushButton()
        btn_type.setCursor(Qt.CursorShape.PointingHandCursor)

        def get_current_type() -> str:
            txt = edit.text().strip()
            if txt.startswith("$"):
                return "var"
            if not txt:
                return default_type
            try:
                int(txt)
                return "int"
            except ValueError:
                try:
                    float(txt)
                    return "float"
                except ValueError:
                    return "str"

        def update_style():
            curr_t = get_current_type()
            if curr_t == "var":
                edit.setStyleSheet("""
                    QLineEdit {
                        background-color: #2e1065;
                        color: #d8b4fe;
                        border: 1.5px solid #a855f7;
                        border-radius: 4px;
                        padding: 3px 6px;
                        font-family: 'Consolas', 'Segoe UI', monospace;
                        font-weight: bold;
                        font-size: 11px;
                    }
                """)
                btn_type.setText("$ Var ▾")
                btn_type.setToolTip("Data Type: Variable ($var). Click to change type or select variable.")
                btn_type.setStyleSheet("""
                    QPushButton {
                        background-color: #3b0764;
                        color: #e9d5ff;
                        font-weight: bold;
                        font-size: 10px;
                        border: 1px solid #9333ea;
                        border-radius: 4px;
                        padding: 3px 7px;
                    }
                    QPushButton:hover {
                        background-color: #581c87;
                        border-color: #c084fc;
                    }
                """)
            else:
                edit.setStyleSheet("""
                    QLineEdit {
                        background-color: #0f172a;
                        color: #f8fafc;
                        border: 1px solid #334155;
                        border-radius: 4px;
                        padding: 3px 6px;
                        font-family: 'Consolas', 'Segoe UI', monospace;
                        font-size: 11px;
                    }
                    QLineEdit:focus {
                        border-color: #38bdf8;
                    }
                """)
                type_label = "123 Int ▾" if curr_t == "int" else ("0.0 Float ▾" if curr_t == "float" else "abc Str ▾")
                btn_type.setText(type_label)
                btn_type.setToolTip(f"Data Type: {curr_t.capitalize()} (Default: {default_type}). Click to switch type or pick variable.")
                btn_type.setStyleSheet("""
                    QPushButton {
                        background-color: #1e293b;
                        color: #94a3b8;
                        font-weight: 600;
                        font-size: 10px;
                        border: 1px solid #475569;
                        border-radius: 4px;
                        padding: 3px 7px;
                    }
                    QPushButton:hover {
                        background-color: #334155;
                        color: #f1f5f9;
                        border-color: #64748b;
                    }
                """)

        update_style()

        # Handle mouse wheel scrolling for quick integer/number adjustment (spinbox feel)
        def handle_wheel(event: QWheelEvent):
            txt = edit.text().strip()
            if not txt.startswith("$"):
                try:
                    val = int(txt) if "." not in txt else float(txt)
                    step = 10 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1
                    delta = 1 if event.angleDelta().y() > 0 else -1
                    new_val = val + (delta * step)
                    edit.setText(str(int(new_val) if isinstance(val, int) else round(new_val, 2)))
                    event.accept()
                    return
                except ValueError:
                    pass
            QLineEdit.wheelEvent(edit, event)

        edit.wheelEvent = handle_wheel

        def on_text(txt):
            update_style()
            val_str = txt.strip()
            if val_str.startswith("$"):
                sc = getattr(self, "node_scene", None) or getattr(self, "scene", None)
                if sc and hasattr(sc, "register_custom_variable"):
                    sc.register_custom_variable(val_str)
                on_change_callback(val_str)
            else:
                try:
                    num = int(val_str)
                    on_change_callback(num)
                except ValueError:
                    try:
                        f_num = float(val_str)
                        on_change_callback(f_num)
                    except ValueError:
                        on_change_callback(val_str)

        edit.textChanged.connect(on_text)
        layout.addWidget(edit, 1)

        def show_type_menu():
            menu = QMenu(container)
            menu.setStyleSheet("""
                QMenu {
                    background-color: #1e293b;
                    color: #f1f5f9;
                    border: 1px solid #475569;
                    padding: 4px;
                }
                QMenu::item {
                    padding: 4px 16px;
                    border-radius: 3px;
                }
                QMenu::item:selected {
                    background-color: #6366f1;
                    color: white;
                }
                QMenu::separator {
                    height: 1px;
                    background-color: #334155;
                    margin: 4px 0px;
                }
            """)

            curr_t = get_current_type()

            # Data Type Section Header
            act_header_dt = menu.addAction("── DATA TYPE (Default: Integer) ──")
            act_header_dt.setEnabled(False)

            # Option 1: Integer (Default)
            is_int = (curr_t == "int")
            act_int = menu.addAction(f"{'✔ ' if is_int else '   '}123 Integer (int)  [Default]")
            def set_int(_=False):
                txt = edit.text().strip()
                if txt.startswith("$") or not txt:
                    edit.setText("0")
                else:
                    try:
                        edit.setText(str(int(float(txt))))
                    except ValueError:
                        edit.setText("0")
            act_int.triggered.connect(set_int)

            # Option 2: Decimal (Float)
            is_float = (curr_t == "float")
            act_float = menu.addAction(f"{'✔ ' if is_float else '   '}0.0 Decimal (float)")
            def set_float(_=False):
                txt = edit.text().strip()
                try:
                    edit.setText(str(float(txt.lstrip("$") or 0.0)))
                except ValueError:
                    edit.setText("0.0")
            act_float.triggered.connect(set_float)

            # Option 3: Text (String)
            is_str = (curr_t == "str")
            act_str = menu.addAction(f"{'✔ ' if is_str else '   '}abc Text (str)")
            def set_str(_=False):
                txt = edit.text().strip().lstrip("$")
                edit.setText(txt or "text")
            act_str.triggered.connect(set_str)

            menu.addSeparator()

            # Variable Section Header
            act_header_var = menu.addAction("── INSERT VARIABLE ($) ──")
            act_header_var.setEnabled(False)

            known = self._get_known_variables()
            for v in known:
                is_active = (edit.text().strip() == v)
                act_v = menu.addAction(f"{'✔ ' if is_active else '   '}$ {v}")
                act_v.triggered.connect(lambda checked=False, var_name=v: edit.setText(var_name))

            menu.addSeparator()

            def add_custom_var(_=False):
                name, ok = QInputDialog.getText(container, "Insert Variable", "Variable name (e.g. count or $y):")
                if ok and name.strip():
                    vn = name.strip()
                    if not vn.startswith("$"):
                        vn = f"${vn}"
                    sc = getattr(self, "node_scene", None) or getattr(self, "scene", None)
                    if sc and hasattr(sc, "register_custom_variable"):
                        sc.register_custom_variable(vn)
                    edit.setText(vn)

            act_cust = menu.addAction("➕ Custom Variable...")
            act_cust.triggered.connect(add_custom_var)

            menu.exec(btn_type.mapToGlobal(QPoint(0, btn_type.height())))

        btn_type.clicked.connect(lambda checked=False: show_type_menu())
        layout.addWidget(btn_type)

        return container, edit

    def _build_action_controls(self, node: ActionNodeItem):
        at = node.properties.get("action_type", node.node_type)

        # 1. Action Type Selector at top of inspector
        type_box = QFrame()
        type_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 8px;")
        tb_layout = QVBoxLayout(type_box)
        tb_layout.setSpacing(6)

        lbl_type = QLabel("Action Category / Type")
        lbl_type.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl_type.setStyleSheet("color: #38bdf8;")
        tb_layout.addWidget(lbl_type)

        combo_type = QComboBox()
        actions_list = [
            ("click", "🖱 Mouse Click"),
            ("dblclick", "🖱 Double Click"),
            ("down", "🖱 Mouse Down (Hold)"),
            ("up", "🖱 Mouse Up (Release)"),
            ("move", "🏹 Mouse Move"),
            ("delay", "⏳ Delay Wait"),
            ("type", "🔤 Type Text"),
            ("key_press", "⌨ Key Press (Tap)"),
            ("key_down", "⌨ Key Down (Hold)"),
            ("key_up", "⌨ Key Up (Release)"),
            ("wheel", "📜 Mouse Wheel"),
        ]
        curr_idx = 0
        for idx, (k, label) in enumerate(actions_list):
            combo_type.addItem(label, k)
            if k == at:
                curr_idx = idx

        combo_type.setCurrentIndex(curr_idx)

        def on_type_changed(idx):
            new_key = combo_type.itemData(idx)
            if new_key and new_key != at:
                node.set_action_type(new_key)
                self.set_node(node)
                self.property_changed.emit()

        combo_type.currentIndexChanged.connect(on_type_changed)
        tb_layout.addWidget(combo_type)
        self.content_layout.addWidget(type_box)

        # 2. Specific controls based on action type
        if at in ("click", "dblclick", "down", "up", "move") or at not in ("delay", "type", "key_press", "key_down", "key_up", "wheel"):
            coord_box = QFrame()
            coord_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 8px;")
            cb_layout = QVBoxLayout(coord_box)
            cb_layout.setSpacing(8)

            lbl_xy = QLabel("Target Screen Position")
            lbl_xy.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl_xy.setStyleSheet("color: #e2e8f0;")
            cb_layout.addWidget(lbl_xy)

            row_xy = QHBoxLayout()
            row_xy.addWidget(QLabel("X:"))
            widget_x, edit_x = self._create_param_input(
                node.properties.get("x", 0),
                lambda val: (node.properties.__setitem__("x", val), node.update(), self.property_changed.emit()),
                placeholder="0 or $x",
                tooltip="Target X coordinate or variable (e.g. 500 or $x)",
            )
            row_xy.addWidget(widget_x)

            row_xy.addWidget(QLabel("Y:"))
            widget_y, edit_y = self._create_param_input(
                node.properties.get("y", 0),
                lambda val: (node.properties.__setitem__("y", val), node.update(), self.property_changed.emit()),
                placeholder="0 or $y",
                tooltip="Target Y coordinate or variable (e.g. 300 or $y)",
            )
            row_xy.addWidget(widget_y)
            cb_layout.addLayout(row_xy)

            # Eye dropper button for sampling coordinate on screen!
            btn_dropper = QPushButton("🎯 Sample Coord (Eye Dropper)")
            btn_dropper.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: white;
                    font-weight: 600;
                    padding: 5px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                }
            """)

            def on_pick_coord():
                parent_win = self.window()
                if parent_win:
                    parent_win.showMinimized()

                dropper = CoordinateEyeDropper(parent=None)

                def on_picked(x, y, hex_col, rgb):
                    edit_x.setText(str(x))
                    edit_y.setText(str(y))
                    node.properties["x"] = x
                    node.properties["y"] = y
                    node.update()
                    self.property_changed.emit()
                    if parent_win:
                        parent_win.showNormal()
                        parent_win.activateWindow()

                dropper.coord_picked.connect(on_picked)
                dropper.rejected.connect(lambda: parent_win.showNormal() if parent_win else None)
                dropper.exec()

            btn_dropper.clicked.connect(on_pick_coord)
            cb_layout.addWidget(btn_dropper)

            # Button selector for click/press actions
            if at in ("click", "dblclick", "down", "up"):
                row_btn = QHBoxLayout()
                row_btn.addWidget(QLabel("Button:"))
                combo_btn = QComboBox()
                combo_btn.addItems(["Left", "Right", "Middle"])
                curr_btn = str(node.properties.get("button", "left")).capitalize()
                idx = combo_btn.findText(curr_btn)
                if idx >= 0:
                    combo_btn.setCurrentIndex(idx)

                def on_btn_changed(txt):
                    node.properties["button"] = txt.lower()
                    node.update()
                    self.property_changed.emit()

                combo_btn.currentTextChanged.connect(on_btn_changed)
                row_btn.addWidget(combo_btn)
                cb_layout.addLayout(row_btn)

            # Move node options: Direct Jump vs. in-between trajectory
            elif at == "move":
                move_opts_box = QFrame()
                move_opts_box.setStyleSheet(
                    "background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 8px;"
                )
                mob_layout = QVBoxLayout(move_opts_box)
                mob_layout.setSpacing(6)

                chk_direct = QCheckBox("Direct Jump (Skip in-between movements)")
                chk_direct.setObjectName("DirectJumpCheckbox")
                chk_direct.setStyleSheet("color: #f1f5f9; font-weight: 600; font-size: 11px;")
                chk_direct.setChecked(bool(node.properties.get("direct_jump", True)))

                path_pts = node.properties.get("path_points", [])
                pts_count = len(path_pts)
                if pts_count > 1:
                    lbl_pts = QLabel(f"📍 Recorded Path: {pts_count} trajectory points stored")
                    lbl_pts.setStyleSheet("color: #38bdf8; font-size: 11px;")
                else:
                    lbl_pts = QLabel("📍 Single target destination (no path recorded)")
                    lbl_pts.setStyleSheet("color: #64748b; font-size: 11px;")

                def on_direct_toggled(checked):
                    node.properties["direct_jump"] = bool(checked)
                    node.update()
                    self.property_changed.emit()

                chk_direct.toggled.connect(on_direct_toggled)
                mob_layout.addWidget(chk_direct)
                mob_layout.addWidget(lbl_pts)
                cb_layout.addWidget(move_opts_box)

            self.content_layout.addWidget(coord_box)

        elif at == "delay":
            delay_box = QFrame()
            delay_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 8px;")
            db_layout = QVBoxLayout(delay_box)

            lbl_d = QLabel("Wait Duration")
            lbl_d.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl_d.setStyleSheet("color: #e2e8f0;")
            db_layout.addWidget(lbl_d)

            row_d = QHBoxLayout()
            row_d.addWidget(QLabel("Milliseconds:"))
            widget_dur, edit_dur = self._create_param_input(
                node.properties.get("duration", 500),
                lambda val: (node.properties.__setitem__("duration", val), node.update(), self.property_changed.emit()),
                placeholder="500 or $delay",
                tooltip="Delay in ms or variable (e.g. 500 or $wait)",
            )
            row_d.addWidget(widget_dur)
            db_layout.addLayout(row_d)

            # Quick presets
            preset_row = QHBoxLayout()
            for ms in (100, 250, 500, 1000, 2000):
                p_btn = QPushButton(f"{ms}ms" if ms < 1000 else f"{ms//1000}s")
                p_btn.setStyleSheet("padding: 2px 4px; font-size: 10px; background: #334155; color: #f1f5f9;")
                p_btn.clicked.connect(lambda _, m=ms: edit_dur.setText(str(m)))
                preset_row.addWidget(p_btn)
            db_layout.addLayout(preset_row)

            self.content_layout.addWidget(delay_box)

        elif at == "type":
            type_box = QFrame()
            type_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 8px;")
            tb_layout = QVBoxLayout(type_box)

            lbl_t = QLabel("Text to Type")
            lbl_t.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl_t.setStyleSheet("color: #e2e8f0;")
            tb_layout.addWidget(lbl_t)

            # Spacious multi-line typing field
            txt_edit = QPlainTextEdit(node.properties.get("value", ""))
            txt_edit.setFixedHeight(110)
            txt_edit.setPlaceholderText("Enter the exact text string or phrase to type...")
            txt_edit.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #0f172a;
                    color: #f8fafc;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 6px;
                    font-family: 'Consolas', monospace;
                    font-size: 12px;
                }
                QPlainTextEdit:focus {
                    border-color: #38bdf8;
                }
            """)

            lbl_len = QLabel(f"Characters: {len(txt_edit.toPlainText())}")
            lbl_len.setStyleSheet("color: #94a3b8; font-size: 10px;")

            def on_txt_changed():
                val = txt_edit.toPlainText()
                node.properties["value"] = val
                lbl_len.setText(f"Characters: {len(val)}")
                node.update()
                self.property_changed.emit()

            txt_edit.textChanged.connect(on_txt_changed)
            tb_layout.addWidget(txt_edit)
            tb_layout.addWidget(lbl_len)

            btn_clear = QPushButton("Clear Text")
            btn_clear.setStyleSheet("background: #334155; color: #f87171; font-size: 10px; padding: 3px;")
            btn_clear.clicked.connect(lambda: txt_edit.clear())
            tb_layout.addWidget(btn_clear)

            self.content_layout.addWidget(type_box)

        elif at in ("key_press", "key_down", "key_up"):
            k_box = QFrame()
            k_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 8px;")
            kb_layout = QVBoxLayout(k_box)
            kb_layout.setSpacing(8)

            title_desc = "Key Press (Tap)" if at == "key_press" else ("Key Down (Hold)" if at == "key_down" else "Key Up (Release)")
            lbl_k = QLabel(f"⌨ {title_desc}")
            lbl_k.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl_k.setStyleSheet("color: #f472b6;")
            kb_layout.addWidget(lbl_k)

            # Common quick-select key pills
            kb_layout.addWidget(QLabel("Quick Pick:"))
            pills_flow = QHBoxLayout()
            pills_flow.setSpacing(4)
            pills_row1 = QHBoxLayout()
            pills_row1.setSpacing(4)
            quick_keys = [
                ("Enter", 0x0D),
                ("Space", 0x20),
                ("Tab", 0x09),
                ("Esc", 0x1B),
                ("Backspace", 0x08),
                ("Delete", 0x2E),
            ]
            quick_keys_row2 = [
                ("Shift", 0x10),
                ("Ctrl", 0x11),
                ("Alt", 0x12),
                ("A", 0x41),
                ("Num 0", 0x60),
                ("F5", 0x74),
            ]

            # Virtual Key spinbox
            row_vk = QHBoxLayout()
            row_vk.addWidget(QLabel("Virtual Key (VK):"))
            spin_vk = QSpinBox()
            spin_vk.setRange(1, 255)
            try:
                vk_val = int(node.properties.get("vk", 13))
            except (ValueError, TypeError):
                vk_val = 13
            spin_vk.setValue(vk_val)
            row_vk.addWidget(spin_vk)

            # Categorized complete keys dropdown
            combo_keys = QComboBox()
            combo_keys.setMaxVisibleItems(25)
            
            # Populate from complete KEY_CATALOG_GROUPS
            model = combo_keys.model()
            item_row = 0
            for group_name, keys in KEY_CATALOG_GROUPS:
                combo_keys.addItem(f"── {group_name} ──", None)
                if model:
                    item = model.index(item_row, 0)
                    if hasattr(model, "itemFromIndex"):
                        std_item = model.itemFromIndex(item)
                        if std_item:
                            std_item.setEnabled(False)
                            std_item.setForeground(QColor("#38bdf8"))
                item_row += 1
                for kname, vk_code in keys:
                    combo_keys.addItem(f"   {kname} (VK {vk_code})", vk_code)
                    item_row += 1

            # Select matching item
            def _sync_combo_to_vk(code):
                for i in range(combo_keys.count()):
                    if combo_keys.itemData(i) == code:
                        combo_keys.blockSignals(True)
                        combo_keys.setCurrentIndex(i)
                        combo_keys.blockSignals(False)
                        break

            _sync_combo_to_vk(vk_val)

            def _apply_key(name: str, code: int):
                node.properties["key"] = name
                node.properties["vk"] = code
                spin_vk.blockSignals(True)
                spin_vk.setValue(code)
                spin_vk.blockSignals(False)
                _sync_combo_to_vk(code)
                node.update()
                self.property_changed.emit()

            # Build pill buttons
            for kname, vk_code in quick_keys:
                btn = QPushButton(kname)
                btn.setStyleSheet("background: #334155; color: #f1f5f9; font-size: 10px; padding: 2px 5px; border-radius: 3px;")
                btn.clicked.connect(lambda _, n=kname, c=vk_code: _apply_key(n, c))
                pills_row1.addWidget(btn)
            kb_layout.addLayout(pills_row1)

            pills_row2 = QHBoxLayout()
            pills_row2.setSpacing(4)
            for kname, vk_code in quick_keys_row2:
                btn = QPushButton(kname)
                btn.setStyleSheet("background: #334155; color: #f1f5f9; font-size: 10px; padding: 2px 5px; border-radius: 3px;")
                btn.clicked.connect(lambda _, n=kname, c=vk_code: _apply_key(n, c))
                pills_row2.addWidget(btn)
            kb_layout.addLayout(pills_row2)

            def on_key_preset(idx):
                code = combo_keys.itemData(idx)
                if code is not None:
                    raw_text = combo_keys.itemText(idx).strip()
                    clean_name = raw_text.split(" (")[0].strip()
                    _apply_key(clean_name, code)

            combo_keys.currentIndexChanged.connect(on_key_preset)
            kb_layout.addWidget(QLabel("Full Key Catalog (All Keys & Numpad):"))
            kb_layout.addWidget(combo_keys)

            def on_vk_change(v):
                c_name = get_name_for_vk(v)
                _apply_key(c_name, v)

            spin_vk.valueChanged.connect(on_vk_change)
            kb_layout.addLayout(row_vk)

            self.content_layout.addWidget(k_box)

        elif at == "wheel":
            w_box = QFrame()
            w_box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
            wb_layout = QVBoxLayout(w_box)
            wb_layout.setSpacing(8)

            lbl_w = QLabel("Mouse Wheel Scroll")
            lbl_w.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            lbl_w.setStyleSheet("color: #6366f1;")
            wb_layout.addWidget(lbl_w)

            # Target Position Option
            has_pos = ("x" in node.properties and "y" in node.properties)
            chk_pos = QCheckBox("Target Specific Screen Position")
            chk_pos.setChecked(has_pos)
            chk_pos.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: 600;")
            wb_layout.addWidget(chk_pos)

            pos_container = QWidget()
            pos_layout = QVBoxLayout(pos_container)
            pos_layout.setContentsMargins(0, 0, 0, 0)
            pos_layout.setSpacing(6)

            row_xy = QHBoxLayout()
            row_xy.addWidget(QLabel("X:"))
            widget_x, edit_x = self._create_param_input(
                node.properties.get("x", 500),
                lambda val: (node.properties.__setitem__("x", val) if chk_pos.isChecked() else None, node.update(), self.property_changed.emit()),
                placeholder="500 or $x",
                tooltip="Target X coordinate or variable",
            )
            row_xy.addWidget(widget_x)

            row_xy.addWidget(QLabel("Y:"))
            widget_y, edit_y = self._create_param_input(
                node.properties.get("y", 500),
                lambda val: (node.properties.__setitem__("y", val) if chk_pos.isChecked() else None, node.update(), self.property_changed.emit()),
                placeholder="500 or $y",
                tooltip="Target Y coordinate or variable",
            )
            row_xy.addWidget(widget_y)
            pos_layout.addLayout(row_xy)

            btn_dropper = QPushButton("🎯 Sample Coord (Eye Dropper)")
            btn_dropper.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: white;
                    font-weight: 600;
                    padding: 4px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                }
            """)

            def on_pick_coord():
                parent_win = self.window()
                if parent_win:
                    parent_win.showMinimized()
                dropper = CoordinateEyeDropper(parent=None)

                def on_picked(x, y, hex_col, rgb):
                    edit_x.setText(str(x))
                    edit_y.setText(str(y))
                    node.properties["x"] = x
                    node.properties["y"] = y
                    node.update()
                    self.property_changed.emit()
                    if parent_win:
                        parent_win.showNormal()
                        parent_win.activateWindow()

                dropper.coord_picked.connect(on_picked)
                dropper.rejected.connect(lambda: parent_win.showNormal() if parent_win else None)
                dropper.exec()

            btn_dropper.clicked.connect(on_pick_coord)
            pos_layout.addWidget(btn_dropper)
            wb_layout.addWidget(pos_container)

            pos_container.setVisible(has_pos)

            def on_toggle_pos(checked):
                pos_container.setVisible(checked)
                if checked:
                    val_x = edit_x.text().strip()
                    try:
                        node.properties["x"] = int(val_x)
                    except (ValueError, TypeError):
                        node.properties["x"] = val_x
                    val_y = edit_y.text().strip()
                    try:
                        node.properties["y"] = int(val_y)
                    except (ValueError, TypeError):
                        node.properties["y"] = val_y
                else:
                    node.properties.pop("x", None)
                    node.properties.pop("y", None)
                node.update()
                self.property_changed.emit()

            chk_pos.toggled.connect(on_toggle_pos)

            # Scroll Direction & Notches
            raw_dy = node.properties.get("deltaY", -120)
            try:
                cur_dy = int(raw_dy)
            except (ValueError, TypeError):
                cur_dy = -120
            is_up = cur_dy >= 0
            cur_notches = max(1, abs(cur_dy) // 120)

            row_dir = QHBoxLayout()
            row_dir.addWidget(QLabel("Scroll Direction:"))
            combo_dir = QComboBox()
            combo_dir.addItems(["▼ Scroll Down", "▲ Scroll Up"])
            combo_dir.setCurrentIndex(1 if is_up else 0)
            row_dir.addWidget(combo_dir)
            wb_layout.addLayout(row_dir)

            row_notches = QHBoxLayout()
            row_notches.addWidget(QLabel("Clicks / Notches:"))
            spin_notches = QSpinBox()
            spin_notches.setRange(1, 100)
            spin_notches.setValue(cur_notches)
            row_notches.addWidget(spin_notches)
            wb_layout.addLayout(row_notches)

            # Quick presets
            btn_row = QHBoxLayout()
            b_down1 = QPushButton("▼ Down 1")
            b_down3 = QPushButton("▼ Down 3")
            b_down5 = QPushButton("▼ Down 5")
            b_up1 = QPushButton("▲ Up 1")
            b_up3 = QPushButton("▲ Up 3")
            btn_row.addWidget(b_down1)
            btn_row.addWidget(b_down3)
            btn_row.addWidget(b_down5)
            btn_row.addWidget(b_up1)
            btn_row.addWidget(b_up3)
            wb_layout.addLayout(btn_row)

            def update_delta_from_ui():
                direction = 1 if combo_dir.currentIndex() == 1 else -1
                notches = spin_notches.value()
                dy = direction * notches * 120
                node.properties["deltaY"] = dy
                node.update()
                self.property_changed.emit()

            combo_dir.currentIndexChanged.connect(lambda _: update_delta_from_ui())
            spin_notches.valueChanged.connect(lambda _: update_delta_from_ui())

            def apply_preset(direction_idx, notches_val):
                combo_dir.setCurrentIndex(direction_idx)
                spin_notches.setValue(notches_val)
                update_delta_from_ui()

            b_down1.clicked.connect(lambda: apply_preset(0, 1))
            b_down3.clicked.connect(lambda: apply_preset(0, 3))
            b_down5.clicked.connect(lambda: apply_preset(0, 5))
            b_up1.clicked.connect(lambda: apply_preset(1, 1))
            b_up3.clicked.connect(lambda: apply_preset(1, 3))

            self.content_layout.addWidget(w_box)

    def _build_if_controls(self, node: IfConditionNodeItem):
        box = QFrame()
        box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        lbl = QLabel("If / Condition Evaluation")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #f59e0b;")
        layout.addWidget(lbl)

        # Variable A
        layout.addWidget(QLabel("Variable A (e.g. $count):"))
        widget_a, edit_a = self._create_param_input(
            node.properties.get("var_a", "$count"),
            lambda val: (node.properties.__setitem__("var_a", str(val)), node.update(), self.property_changed.emit()),
            placeholder="$variable or value",
            tooltip="First variable or operand to compare (e.g. $count, $i, $y)",
        )
        layout.addWidget(widget_a)

        # Operator
        layout.addWidget(QLabel("Comparison Operator:"))
        combo_op = QComboBox()
        ops = [
            "== (Equal)",
            "!= (Not Equal)",
            "> (Greater Than)",
            "< (Less Than)",
            ">= (Greater or Equal)",
            "<= (Less or Equal)",
            "contains (Text Contains)",
            "is empty",
        ]
        combo_op.addItems(ops)
        curr_op = node.properties.get("operator", "==")
        for i, o in enumerate(ops):
            if o.startswith(curr_op + " ") or o == curr_op:
                combo_op.setCurrentIndex(i)
                break

        def on_op_change(txt):
            raw_op = txt.split(" ")[0]
            node.properties["operator"] = raw_op
            node.update()
            self.property_changed.emit()

        combo_op.currentTextChanged.connect(on_op_change)
        layout.addWidget(combo_op)

        # Value B
        layout.addWidget(QLabel("Value B:"))
        widget_b, edit_b = self._create_param_input(
            node.properties.get("val_b", "5"),
            lambda val: (node.properties.__setitem__("val_b", str(val)), node.update(), self.property_changed.emit()),
            placeholder="5 or $target",
            tooltip="Second value or variable to compare against",
        )
        layout.addWidget(widget_b)

        info = QLabel("Routes flow to 'True' if condition matches, else 'False'.")
        info.setStyleSheet("color: #94a3b8; font-size: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.content_layout.addWidget(box)

    def _build_math_controls(self, node: MathNodeItem):
        box = QFrame()
        box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        lbl = QLabel("Math & Variable Assignment")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #14b8a6;")
        layout.addWidget(lbl)

        # Variable Name
        layout.addWidget(QLabel("Variable Name:"))
        edit_var = QLineEdit(node.properties.get("var_name", "count"))

        def on_var_change(txt):
            clean_name = txt.lstrip("$").strip()
            node.properties["var_name"] = clean_name
            if clean_name:
                sc = getattr(self, "node_scene", None) or getattr(self, "scene", None)
                if sc and hasattr(sc, "register_custom_variable"):
                    sc.register_custom_variable(f"${clean_name}")
            node.update()
            self.property_changed.emit()

        edit_var.textChanged.connect(on_var_change)
        layout.addWidget(edit_var)

        # Operation
        layout.addWidget(QLabel("Operation:"))
        combo_op = QComboBox()
        combo_op.addItems([
            "Increment (+1)",
            "Decrement (-1)",
            "Set Value (=)",
            "Add (+ Value)",
            "Subtract (- Value)",
            "Multiply (* Value)",
            "Random Number (Min..Max)",
        ])
        curr_op = node.properties.get("operation", "increment")
        op_map = {
            "increment": 0, "decrement": 1, "set": 2, "add": 3,
            "subtract": 4, "multiply": 5, "random": 6,
        }
        combo_op.setCurrentIndex(op_map.get(curr_op, 0))

        # Value container
        val_box = QWidget()
        val_layout = QVBoxLayout(val_box)
        val_layout.setContentsMargins(0, 0, 0, 0)
        lbl_v = QLabel("Value:")
        widget_val, edit_val = self._create_param_input(
            node.properties.get("value", "1"),
            lambda val: (node.properties.__setitem__("value", str(val)), node.update(), self.property_changed.emit()),
            placeholder="1 or $step",
            tooltip="Numeric value or variable to assign/calculate",
        )
        val_layout.addWidget(lbl_v)
        val_layout.addWidget(widget_val)

        # Random container
        rand_box = QWidget()
        rand_layout = QHBoxLayout(rand_box)
        rand_layout.setContentsMargins(0, 0, 0, 0)
        spin_min = QSpinBox()
        spin_min.setRange(-100000, 100000)
        try:
            min_v = int(node.properties.get("min_val", 100))
        except (ValueError, TypeError):
            min_v = 100
        spin_min.setValue(min_v)
        spin_max = QSpinBox()
        spin_max.setRange(-100000, 100000)
        try:
            max_v = int(node.properties.get("max_val", 1000))
        except (ValueError, TypeError):
            max_v = 1000
        spin_max.setValue(max_v)
        rand_layout.addWidget(QLabel("Min:"))
        rand_layout.addWidget(spin_min)
        rand_layout.addWidget(QLabel("Max:"))
        rand_layout.addWidget(spin_max)

        def update_visibility(idx):
            val_box.setVisible(idx in (2, 3, 4, 5))
            rand_box.setVisible(idx == 6)

        update_visibility(combo_op.currentIndex())

        def on_op_selected(idx):
            keys = ["increment", "decrement", "set", "add", "subtract", "multiply", "random"]
            node.properties["operation"] = keys[idx]
            update_visibility(idx)
            node.update()
            self.property_changed.emit()

        combo_op.currentIndexChanged.connect(on_op_selected)
        layout.addWidget(combo_op)
        layout.addWidget(val_box)
        layout.addWidget(rand_box)

        spin_min.valueChanged.connect(lambda v: (node.properties.update({"min_val": v}), node.update(), self.property_changed.emit()))
        spin_max.valueChanged.connect(lambda v: (node.properties.update({"max_val": v}), node.update(), self.property_changed.emit()))

        self.content_layout.addWidget(box)

    def _build_pixel_color_controls(self, node: PixelColorNodeItem):
        box = QFrame()
        box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        lbl = QLabel("Pixel Color Verification")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #d946ef;")
        layout.addWidget(lbl)

        # Coordinates
        row_xy = QHBoxLayout()
        row_xy.addWidget(QLabel("X:"))
        widget_x, edit_x = self._create_param_input(
            node.properties.get("x", 0),
            lambda val: (node.properties.__setitem__("x", val), node.update(), self.property_changed.emit()),
            placeholder="0 or $x",
            tooltip="Target screen pixel X coordinate or variable (e.g. 500 or $x)",
        )
        row_xy.addWidget(widget_x)

        row_xy.addWidget(QLabel("Y:"))
        widget_y, edit_y = self._create_param_input(
            node.properties.get("y", 0),
            lambda val: (node.properties.__setitem__("y", val), node.update(), self.property_changed.emit()),
            placeholder="0 or $y",
            tooltip="Target screen pixel Y coordinate or variable (e.g. 300 or $y)",
        )
        row_xy.addWidget(widget_y)
        layout.addLayout(row_xy)

        # Eye dropper button for sampling coordinate AND color together!
        btn_sample = QPushButton("🎯 Pick Color & Coord (Eye Dropper)")
        btn_sample.setStyleSheet("""
            QPushButton {
                background-color: #d946ef;
                color: white;
                font-weight: bold;
                padding: 6px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #c026d3;
            }
        """)

        # Color row: swatch + hex edit
        row_col = QHBoxLayout()
        swatch_lbl = QLabel()
        swatch_lbl.setFixedSize(28, 24)
        curr_hex = node.properties.get("color", "#38BDF8")
        swatch_lbl.setStyleSheet(f"background-color: {curr_hex}; border: 1px solid #ffffff; border-radius: 4px;")
        row_col.addWidget(swatch_lbl)

        edit_hex = QLineEdit(curr_hex)
        row_col.addWidget(edit_hex)

        def update_color(h_str):
            node.properties["color"] = h_str
            swatch_lbl.setStyleSheet(f"background-color: {h_str}; border: 1px solid #ffffff; border-radius: 4px;")
            node.update()
            self.property_changed.emit()

        edit_hex.textChanged.connect(update_color)

        btn_pick_dlg = QPushButton("Palette...")
        btn_pick_dlg.setStyleSheet("padding: 3px 6px; font-size: 11px;")

        def on_open_palette():
            col = QColorDialog.getColor(QColor(node.properties.get("color", "#FFFFFF")), self)
            if col.isValid():
                edit_hex.setText(col.name().upper())

        btn_pick_dlg.clicked.connect(on_open_palette)
        row_col.addWidget(btn_pick_dlg)

        def on_sample():
            parent_win = self.window()
            if parent_win:
                parent_win.showMinimized()

            dropper = CoordinateEyeDropper(parent=None)

            def on_picked(x, y, hex_col, rgb):
                edit_x.setText(str(x))
                edit_y.setText(str(y))
                edit_hex.setText(hex_col)
                node.properties["x"] = x
                node.properties["y"] = y
                node.properties["color"] = hex_col
                node.update()
                self.property_changed.emit()
                if parent_win:
                    parent_win.showNormal()
                    parent_win.activateWindow()

            dropper.coord_picked.connect(on_picked)
            dropper.rejected.connect(lambda: parent_win.showNormal() if parent_win else None)
            dropper.exec()

        btn_sample.clicked.connect(on_sample)
        layout.addWidget(btn_sample)
        layout.addLayout(row_col)

        # Tolerance
        try:
            tol_val = int(node.properties.get("tolerance", 15))
        except (ValueError, TypeError):
            tol_val = 15
        lbl_tol = QLabel(f"Color Tolerance: ±{tol_val}")
        layout.addWidget(lbl_tol)

        slider_tol = QSlider(Qt.Orientation.Horizontal)
        slider_tol.setRange(0, 60)
        slider_tol.setValue(tol_val)

        def on_tol_change(v):
            node.properties["tolerance"] = v
            lbl_tol.setText(f"Color Tolerance: ±{v}")
            node.update()
            self.property_changed.emit()

        slider_tol.valueChanged.connect(on_tol_change)
        layout.addWidget(slider_tol)

        self.content_layout.addWidget(box)

    def _build_hotkey_controls(self, node: HotkeyNodeItem):
        box = QFrame()
        box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        lbl = QLabel("Key Combination (Hotkey)")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #8b5cf6;")
        layout.addWidget(lbl)

        combo_preset = QComboBox()
        presets = [
            "Ctrl+C (Copy)",
            "Ctrl+V (Paste)",
            "Ctrl+A (Select All)",
            "Ctrl+Z (Undo)",
            "Ctrl+S (Save)",
            "Ctrl+Shift+Esc (Task Manager)",
            "Ctrl+Alt+Delete (SAS / Security)",
            "Delete",
            "Shift+Delete",
            "Enter",
            "Escape",
            "Tab",
            "Alt+Tab",
            "Win+D (Show Desktop)",
            "Backspace",
            "Custom...",
        ]
        combo_preset.addItems(presets)

        curr_combo = str(node.properties.get("combo", "Ctrl+C")).strip()
        matched_idx = -1
        for i, p in enumerate(presets):
            if p.split(" ")[0].lower() == curr_combo.lower():
                matched_idx = i
                break
        combo_preset.blockSignals(True)
        if matched_idx >= 0:
            combo_preset.setCurrentIndex(matched_idx)
        else:
            combo_preset.setCurrentIndex(len(presets) - 1)
        combo_preset.blockSignals(False)

        edit_combo = QLineEdit(curr_combo)

        cad_frame = QFrame()
        cad_frame.setStyleSheet("background: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 6px;")
        cad_layout = QVBoxLayout(cad_frame)
        cad_layout.setSpacing(6)

        lbl_cad_note = QLabel(
            "ℹ️ <b>Windows OS Security Restriction:</b><br/>"
            "Windows protects <i>Ctrl+Alt+Delete</i> (SAS). Standard applications are blocked from sending synthetic raw keystrokes. "
            "Choose your intended action below:"
        )
        lbl_cad_note.setWordWrap(True)
        lbl_cad_note.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        cad_layout.addWidget(lbl_cad_note)

        cad_layout.addWidget(QLabel("Action to Execute:"))
        combo_cad_action = QComboBox()
        combo_cad_action.addItem("🚀 Open Task Manager (Recommended)", "taskmgr")
        combo_cad_action.addItem("🔒 Lock Computer / Workstation", "lock")
        combo_cad_action.addItem("🛡️ Security Attention Sequence (SendSAS)", "sas")

        curr_cad_act = node.properties.get("cad_action", "taskmgr")
        idx_act = combo_cad_action.findData(curr_cad_act)
        if idx_act >= 0:
            combo_cad_action.setCurrentIndex(idx_act)

        def on_cad_action_changed(idx):
            act_val = combo_cad_action.itemData(idx)
            node.properties["cad_action"] = act_val
            node.update()
            self.property_changed.emit()

        combo_cad_action.currentIndexChanged.connect(on_cad_action_changed)
        cad_layout.addWidget(combo_cad_action)

        init_norm = str(node.properties.get("combo", "")).lower().replace(" ", "")
        is_cad_init = "ctrl" in init_norm and "alt" in init_norm and ("del" in init_norm or "delete" in init_norm)
        cad_frame.setVisible(is_cad_init)

        def on_preset_selected(idx):
            if idx < len(presets) - 1:
                key = presets[idx].split(" ")[0]
                edit_combo.setText(key)
            elif idx == len(presets) - 1:
                edit_combo.setFocus()
                edit_combo.selectAll()

        combo_preset.currentIndexChanged.connect(on_preset_selected)
        layout.addWidget(QLabel("Preset:"))
        layout.addWidget(combo_preset)

        layout.addWidget(QLabel("Key Combination:"))
        layout.addWidget(edit_combo)
        layout.addWidget(cad_frame)

        def on_combo_changed(txt):
            node.properties["combo"] = txt
            norm = txt.lower().replace(" ", "")
            is_cad = "ctrl" in norm and "alt" in norm and ("del" in norm or "delete" in norm)
            cad_frame.setVisible(is_cad)

            # Sync preset combo box
            combo_preset.blockSignals(True)
            m_idx = -1
            for i, p in enumerate(presets):
                if p.split(" ")[0].lower() == txt.strip().lower():
                    m_idx = i
                    break
            if m_idx >= 0:
                combo_preset.setCurrentIndex(m_idx)
            else:
                combo_preset.setCurrentIndex(len(presets) - 1)
            combo_preset.blockSignals(False)

            node.update()
            self.property_changed.emit()

        edit_combo.textChanged.connect(on_combo_changed)

        self.content_layout.addWidget(box)

    def _build_loop_controls(self, node: LoopNodeItem):
        box = QFrame()
        box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
        layout = QVBoxLayout(box)
        layout.setSpacing(8)

        lbl = QLabel("🔁 Loop & Repeat Controls")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #6366f1;")
        layout.addWidget(lbl)

        # Infinite loop checkbox (default True)
        is_inf = bool(node.properties.get("infinite", True))
        chk_inf = QCheckBox("Infinite Loop (∞)")
        chk_inf.setObjectName("InfiniteLoopCheckbox")
        chk_inf.setChecked(is_inf)
        chk_inf.setStyleSheet("color: #a5b4fc; font-weight: bold; font-size: 11px;")
        layout.addWidget(chk_inf)

        row_cnt = QHBoxLayout()
        lbl_cnt = QLabel("Repeat Count:")
        row_cnt.addWidget(lbl_cnt)
        widget_cnt, edit_cnt = self._create_param_input(
            node.properties.get("count", 5),
            lambda val: (node.properties.__setitem__("count", val), node.update(), self.property_changed.emit()),
            placeholder="5 or $count",
            tooltip="Loop iteration count or variable (e.g. 5 or $total)",
        )
        widget_cnt.setEnabled(not is_inf)
        row_cnt.addWidget(widget_cnt)
        layout.addLayout(row_cnt)

        def on_inf_toggle(state):
            checked = (state == Qt.CheckState.Checked.value or state == True)
            node.properties["infinite"] = checked
            widget_cnt.setEnabled(not checked)
            node.update()
            self.property_changed.emit()

        chk_inf.stateChanged.connect(on_inf_toggle)

        row_var = QHBoxLayout()
        row_var.addWidget(QLabel("Index Variable:"))
        edit_v = QLineEdit(node.properties.get("var_name", "i"))

        def on_var_change(txt):
            clean_name = txt.lstrip("$").strip()
            node.properties["var_name"] = clean_name
            if clean_name:
                sc = getattr(self, "node_scene", None) or getattr(self, "scene", None)
                if sc and hasattr(sc, "register_custom_variable"):
                    sc.register_custom_variable(f"${clean_name}")
            node.update()
            self.property_changed.emit()

        edit_v.textChanged.connect(on_var_change)
        row_var.addWidget(edit_v)
        layout.addLayout(row_var)

        info = QLabel("Body wire runs each iteration; Done wire continues when complete. End of body sequence auto-cycles back into the loop without needing a long backward wire.")
        info.setStyleSheet("color: #94a3b8; font-size: 10px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.content_layout.addWidget(box)

    def _build_stop_controls(self, node: StopNodeItem):
        box = QFrame()
        box.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
        layout = QVBoxLayout(box)
        lbl = QLabel("Stop Playback Node")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #ef4444;")
        layout.addWidget(lbl)
        desc = QLabel("When reached in execution, playback immediately stops.")
        desc.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        self.content_layout.addWidget(box)

    def _build_vision_controls(self, node: VisionNodeItem):
        vbox = QFrame()
        vbox.setStyleSheet("background: #1e293b; border-radius: 6px; padding: 10px;")
        layout = QVBoxLayout(vbox)
        layout.setSpacing(10)

        # Section header
        lbl = QLabel("Wait For Image (Visual Recognition)")
        lbl.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #10b981;")
        layout.addWidget(lbl)

        # Image preview
        lbl_thumb = QLabel()
        lbl_thumb.setFixedHeight(70)
        lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_thumb.setStyleSheet("background: #0f172a; border: 1px dashed #475569; border-radius: 4px;")

        def refresh_thumb():
            tmpl = node.properties.get("template", "")
            if tmpl and os.path.exists(tmpl):
                pix = QPixmap(tmpl)
                if not pix.isNull():
                    scaled = pix.scaled(
                        200, 60, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                    lbl_thumb.setPixmap(scaled)
                    return
            lbl_thumb.setText("No Image Snippet")
            lbl_thumb.setStyleSheet("background: #0f172a; border: 1px dashed #475569; border-radius: 4px; color: #64748b; font-size: 10px;")

        refresh_thumb()
        layout.addWidget(lbl_thumb)

        # Snippet buttons
        btn_snip = QPushButton("📸 Snip from Screen")
        btn_snip.setStyleSheet("background: #0284c7; color: white; font-weight: bold; padding: 6px; border-radius: 4px;")

        def on_snip_click():
            parent_win = self.window()
            if parent_win:
                parent_win.showMinimized()

            snipper = ScreenSnipper(parent=None)

            def on_captured(qimg, filepath):
                node.update_template(filepath)
                refresh_thumb()
                self.property_changed.emit()
                if parent_win:
                    parent_win.showNormal()
                    parent_win.activateWindow()

            snipper.snippet_captured.connect(on_captured)
            snipper.rejected.connect(lambda: parent_win.showNormal() if parent_win else None)
            snipper.exec()

        btn_snip.clicked.connect(on_snip_click)
        layout.addWidget(btn_snip)

        btn_browse = QPushButton("📂 Browse File...")
        btn_browse.setStyleSheet("background: #334155; color: #e2e8f0; padding: 5px; border-radius: 4px;")

        def on_browse():
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Template Image", "", "Images (*.png *.jpg *.bmp)"
            )
            if path:
                node.update_template(path)
                refresh_thumb()
                self.property_changed.emit()

        btn_browse.clicked.connect(on_browse)
        layout.addWidget(btn_browse)

        # Confidence Slider
        try:
            curr_conf = int(float(node.properties.get("confidence", 0.85)) * 100)
        except (ValueError, TypeError):
            curr_conf = 85
        lbl_conf = QLabel(f"Match Confidence: {curr_conf}%")
        lbl_conf.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        layout.addWidget(lbl_conf)

        slider_conf = QSlider(Qt.Orientation.Horizontal)
        slider_conf.setRange(50, 99)
        slider_conf.setValue(curr_conf)

        def on_conf_change(val):
            node.properties["confidence"] = val / 100.0
            lbl_conf.setText(f"Match Confidence: {val}%")
            node.update()
            self.property_changed.emit()

        slider_conf.valueChanged.connect(on_conf_change)
        layout.addWidget(slider_conf)

        # Action on Found
        row_act = QHBoxLayout()
        row_act.addWidget(QLabel("On Found:"))
        combo_act = QComboBox()
        combo_act.addItems(["None", "Click", "Double Click", "Move"])
        act_map = {
            "click": "Click",
            "doubleclick": "Double Click",
            "dblclick": "Double Click",
            "move": "Move",
            "none": "None",
        }
        raw_act = str(node.properties.get("action", "none")).lower().replace(" ", "")
        disp_act = act_map.get(raw_act, "None")
        idx = combo_act.findText(disp_act)
        if idx >= 0:
            combo_act.setCurrentIndex(idx)

        def on_act_change(txt):
            rev_map = {
                "Click": "click",
                "Double Click": "doubleclick",
                "Move": "move",
                "None": "none",
            }
            node.properties["action"] = rev_map.get(txt, "none")
            node.update()
            self.property_changed.emit()

        combo_act.currentTextChanged.connect(on_act_change)
        row_act.addWidget(combo_act)
        layout.addLayout(row_act)

        # Timeout (sec)
        row_tout = QHBoxLayout()
        row_tout.addWidget(QLabel("Timeout (sec):"))
        spin_tout = QDoubleSpinBox()
        spin_tout.setRange(0.1, 300.0)
        spin_tout.setDecimals(1)
        spin_tout.setSingleStep(0.5)
        try:
            tout_val = float(node.properties.get("timeout", 5.0))
        except (ValueError, TypeError):
            tout_val = 5.0
        spin_tout.setValue(tout_val)
        spin_tout.setCursor(Qt.CursorShape.ArrowCursor)

        def on_tout_change(val):
            node.properties["timeout"] = val
            node.update()
            self.property_changed.emit()

        spin_tout.valueChanged.connect(on_tout_change)
        row_tout.addWidget(spin_tout)
        layout.addLayout(row_tout)

        # Loop Until Found / Break out toggle
        row_break = QHBoxLayout()
        chk_break = QCheckBox("🎯 Loop Until Found (Break on Detection)")
        chk_break.setObjectName("BreakLoopCheckbox")
        chk_break.setChecked(bool(node.properties.get("break_loop_on_found", False)))
        chk_break.setStyleSheet("color: #34d399; font-weight: bold; font-size: 11px;")

        def on_break_change(state):
            checked = (state == Qt.CheckState.Checked.value or state == True)
            node.properties["break_loop_on_found"] = checked
            node.update()
            self.property_changed.emit()

        chk_break.stateChanged.connect(on_break_change)
        row_break.addWidget(chk_break)
        layout.addLayout(row_break)

        desc_break = QLabel("When enabled: detecting the image immediately breaks out of the enclosing loop to the exit/Done step.")
        desc_break.setStyleSheet("color: #94a3b8; font-size: 10px;")
        desc_break.setWordWrap(True)
        layout.addWidget(desc_break)

        self.content_layout.addWidget(vbox)
