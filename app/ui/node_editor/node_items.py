"""Graphics items for nodes in the node editor."""

from __future__ import annotations

import os
import uuid
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QPixmap,
    QImage,
)
from PyQt6.QtWidgets import QGraphicsItem

from app.ui.node_editor.node_socket import NodeSocketItem
from app.core.key_catalog import get_name_for_vk

if TYPE_CHECKING:
    from app.ui.node_editor.node_group import NodeGroupItem
    from app.ui.node_editor.node_scene import NodeScene


class BaseNodeItem(QGraphicsItem):
    """Base class for all visual nodes in the flow editor."""

    def __init__(
        self,
        title: str = "Node",
        node_type: str = "action",
        color: Optional[QColor] = None,
        properties: Optional[Dict[str, Any]] = None,
        parent: Optional[QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.id = getattr(self, "id", None) or uuid.uuid4().hex[:8]
        self.title = title
        self.node_type = node_type
        self.accent_color = color or QColor(56, 189, 248)  # Cyan default

        self.width = 190.0
        self.height = 85.0
        self.header_height = 28.0

        self.input_sockets: List[NodeSocketItem] = []
        self.output_sockets: List[NodeSocketItem] = []
        self.group: Optional["NodeGroupItem"] = None

        # Data properties dictionary for serialization and execution
        self.properties: Dict[str, Any] = dict(properties) if properties else {}
        self.bypassed: bool = bool(self.properties.get("bypassed", False))
        self.is_executing: bool = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(1)

    def clone(self) -> "BaseNodeItem":
        """Create a clone instance of this node with copied properties."""
        cls = self.__class__
        new_node = cls(node_type=self.node_type, properties=dict(self.properties))
        new_node.bypassed = self.bypassed
        return new_node

    def set_bypassed(self, state: bool):
        self.bypassed = bool(state)
        self.properties["bypassed"] = self.bypassed
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-10, -10, self.width + 20, self.height + 20)

    def add_input_socket(self, name: str = "In", color: Optional[QColor] = None) -> NodeSocketItem:
        socket = NodeSocketItem(self, NodeSocketItem.TYPE_INPUT, name=name, color=color)
        self.input_sockets.append(socket)
        self._layout_sockets()
        return socket

    def add_output_socket(self, name: str = "Out", color: Optional[QColor] = None) -> NodeSocketItem:
        socket = NodeSocketItem(self, NodeSocketItem.TYPE_OUTPUT, name=name, color=color)
        self.output_sockets.append(socket)
        self._layout_sockets()
        return socket

    def _layout_sockets(self):
        # Input sockets along the left edge (x=0)
        n_in = len(self.input_sockets)
        for i, sock in enumerate(self.input_sockets):
            sy = self.header_height + (self.height - self.header_height) * (i + 1) / (n_in + 1)
            sock.setPos(0, sy)

        # Output sockets along the right edge (x=self.width)
        n_out = len(self.output_sockets)
        for i, sock in enumerate(self.output_sockets):
            sy = self.header_height + (self.height - self.header_height) * (i + 1) / (n_out + 1)
            sock.setPos(self.width, sy)

    def update_connected_wires(self):
        """Update all bezier curve connection wires attached to this node's sockets."""
        for sock in self.input_sockets + self.output_sockets:
            sock.update_connections()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Update all connected wires when node moves
            self.update_connected_wires()
            if self.scene() and hasattr(self.scene(), "update_loop_bounds"):
                self.scene().update_loop_bounds()
        return super().itemChange(change, value)

    def get_summary_text(self) -> str:
        """Returns brief text for node body."""
        return ""

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self.width, self.height)
        is_sel = self.isSelected()

        # If bypassed, reduce overall opacity
        if self.bypassed:
            painter.setOpacity(0.55)

        # Body background
        painter.setPen(Qt.PenStyle.NoPen)
        body_color = QColor(24, 28, 38) if self.bypassed else QColor(30, 41, 59)
        painter.setBrush(QBrush(body_color))
        painter.drawRoundedRect(rect, 8, 8)

        # Header background
        header_rect = QRectF(0, 0, self.width, self.header_height)
        hdr_color = QColor(71, 85, 105) if self.bypassed else self.accent_color
        painter.setBrush(QBrush(hdr_color))
        painter.drawRoundedRect(header_rect, 8, 8)
        # Flatten bottom corners of header
        painter.fillRect(QRectF(0, self.header_height - 6, self.width, 6), hdr_color)

        # Border
        if getattr(self, "is_executing", False):
            glow_pen = QPen(QColor(16, 185, 129, 120), 7.0)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 8, 8)
            border_col = QColor(16, 185, 129)
            pen = QPen(border_col, 3.2)
        elif is_sel:
            border_col = QColor(251, 146, 60)
            pen = QPen(border_col, 2.5)
        elif self.bypassed:
            border_col = QColor(245, 158, 11)  # Amber dashed
            pen = QPen(border_col, 1.8, Qt.PenStyle.DashLine)
        else:
            border_col = QColor(71, 85, 105)
            pen = QPen(border_col, 1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 8, 8)

        # Header Title
        painter.setPen(QColor(255, 255, 255) if not self.bypassed else QColor(203, 213, 225))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        text_rect = QRectF(10, 0, self.width - 20, self.header_height)
        display_title = f"{self.title} [BYPASSED]" if self.bypassed else self.title
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            display_title,
        )

        # Executing Running Badge
        if getattr(self, "is_executing", False):
            badge_w = 64
            badge_rect = QRectF(self.width - badge_w - 6, 4, badge_w, self.header_height - 8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(16, 185, 129)))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "⚡ RUNNING")

        # Body summary text
        summary = self.get_summary_text()
        if summary:
            painter.setPen(QColor(148, 163, 184) if self.bypassed else QColor(203, 213, 225))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Normal))
            body_rect = QRectF(12, self.header_height + 4, self.width - 24, self.height - self.header_height - 8)
            painter.drawText(
                body_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                summary,
            )

        # If bypassed, draw a distinct strikethrough line across header title
        if self.bypassed:
            painter.setPen(QPen(QColor(245, 158, 11, 220), 2))
            painter.drawLine(8, int(self.header_height / 2), int(self.width - 8), int(self.header_height / 2))


class StartNodeItem(BaseNodeItem):
    """Entry point node for macro execution."""

    def __init__(self, parent=None):
        super().__init__(
            title="▶ Start",
            node_type="start",
            color=QColor(16, 185, 129),  # Emerald
            parent=parent,
        )
        self.width = 130.0
        self.height = 60.0
        self.add_output_socket(name="Out")

    def get_summary_text(self) -> str:
        return "Begin execution"


class ActionNodeItem(BaseNodeItem):
    """Action node (Click, Double Click, Mouse Down, Mouse Up, Move, Delay, Key, Type, Wheel)."""

    COLORS = {
        "click": QColor(56, 189, 248),      # Cyan
        "dblclick": QColor(14, 165, 233),   # Sky blue
        "down": QColor(59, 130, 246),       # Blue
        "up": QColor(99, 102, 241),         # Indigo
        "move": QColor(168, 85, 247),       # Purple
        "delay": QColor(245, 158, 11),      # Amber
        "key_press": QColor(244, 63, 94),   # Rose / Coral
        "key_down": QColor(236, 72, 153),   # Pink
        "key_up": QColor(217, 70, 239),     # Fuchsia
        "type": QColor(168, 85, 247),       # Purple
        "wheel": QColor(99, 102, 241),      # Indigo
        "action": QColor(71, 85, 105),      # Slate
    }

    TITLES = {
        "click": "🖱 Mouse Click",
        "dblclick": "🖱 Double Click",
        "down": "🖱 Mouse Down (Hold)",
        "up": "🖱 Mouse Up (Release)",
        "move": "🏹 Mouse Move",
        "delay": "⏳ Delay Wait",
        "key_press": "⌨ Key Press (Tap)",
        "key_down": "⌨ Key Down (Hold)",
        "key_up": "⌨ Key Up (Release)",
        "type": "🔤 Type Text",
        "wheel": "📜 Mouse Wheel",
        "action": "⚙ Custom Action",
    }

    def __init__(
        self,
        action_type: str = "click",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        props = properties or {}

        super().__init__(
            title=self.TITLES.get(action_type, "⚙ Action"),
            node_type=action_type,
            color=self.COLORS.get(action_type, QColor(56, 189, 248)),
            parent=parent,
        )
        self.properties = dict(props)
        self.properties.setdefault("action_type", action_type)
        if action_type == "key_down":
            self.properties.setdefault("auto_repeat", True)
            self.properties.setdefault("hold_duration", 0)
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.add_input_socket(name="In")
        self.add_output_socket(name="Out")

    def set_action_type(self, new_type: str):
        self.node_type = new_type
        self.properties["action_type"] = new_type
        if new_type == "key_down":
            self.properties.setdefault("auto_repeat", True)
            self.properties.setdefault("hold_duration", 0)
        self.title = self.TITLES.get(new_type, "⚙ Action")
        self.accent_color = self.COLORS.get(new_type, QColor(56, 189, 248))
        self.update()

    def get_summary_text(self) -> str:
        at = self.properties.get("action_type", self.node_type)
        if at in ("click", "dblclick", "down", "up"):
            x = self.properties.get("x", 0)
            y = self.properties.get("y", 0)
            btn = self.properties.get("button", "left").capitalize()
            desc = "Click" if at == "click" else ("Double Click" if at == "dblclick" else ("Down" if at == "down" else "Up"))
            return f"{btn} {desc}\nX: {x},  Y: {y}"
        elif at == "move":
            x = self.properties.get("x", 0)
            y = self.properties.get("y", 0)
            direct = self.properties.get("direct_jump", True)
            pts = len(self.properties.get("path_points", []))
            mode = "Direct" if direct else (f"Path ({pts} pts)" if pts > 1 else "Path")
            return f"Move ({mode})\nX: {x},  Y: {y}"
        elif at == "delay":
            ms = self.properties.get("duration", 500)
            try:
                ms_num = float(ms)
                return f"Pause for {ms_num:.0f} ms\n({ms_num/1000.0:.2f} seconds)"
            except (ValueError, TypeError):
                return f"Pause for {ms} ms\n(Variable delay)"
        elif at == "type":
            txt = str(self.properties.get("value", ""))
            disp = (txt[:18] + "..") if len(txt) > 20 else txt
            return f"Type text:\n\"{disp}\""
        elif at in ("key_press", "key_down", "key_up"):
            vk = self.properties.get("vk")
            key_name = self.properties.get("key")
            if not key_name and vk:
                key_name = get_name_for_vk(vk)
            disp = key_name if key_name else (f"VK {vk}" if vk else "Unset")
            if at == "key_press":
                return f"Tap Key: {disp}\n(Press & Release)"
            elif at == "key_down":
                hold_dur = self.properties.get("hold_duration", 0)
                rep = " [Repeat]" if self.properties.get("auto_repeat", False) else ""
                if hold_dur:
                    return f"Hold Key: {disp}\n({hold_dur}ms{rep})"
                return f"Hold Key: {disp}\n(Key Down)"
            else:
                return f"Release Key: {disp}\n(Key Up)"
        elif at == "wheel":
            raw_dy = self.properties.get("deltaY", 120)
            try:
                dy = int(raw_dy)
                notches = abs(dy) // 120 or 1
                direction = "Up ▲" if dy >= 0 else "Down ▼"
                desc = f"Scroll {direction} ({notches} notch)"
            except (ValueError, TypeError):
                desc = f"Scroll: {raw_dy}"
            x = self.properties.get("x")
            y = self.properties.get("y")
            loc_str = f" at ({x}, {y})" if (x is not None and y is not None) else " (At Cursor)"
            return f"{desc}{loc_str}"
        return f"Action: {at}"

    def clone(self) -> "ActionNodeItem":
        return ActionNodeItem(
            action_type=self.node_type,
            properties=dict(self.properties),
        )


class VisionNodeItem(BaseNodeItem):
    """Smart AI vision node: finds template image or waits for it on screen."""

    def __init__(
        self,
        vision_type: str = "wait_image",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="⏱ Wait For Image",
            node_type="wait_image",
            color=QColor(16, 185, 129),  # Emerald
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "wait_image")
        self.properties.setdefault("confidence", 0.85)
        self.properties.setdefault("action", "none")
        self.properties.setdefault("button", "left")
        self.properties.setdefault("timeout", 5.0)
        self.properties.setdefault("template", "")
        self.properties.setdefault("break_loop_on_found", False)
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 210.0
        self.height = 135.0  # Room for snippet preview thumbnail!

        self.thumbnail_pixmap: Optional[QPixmap] = None
        self._load_thumbnail()

        # Sockets: 1 Input, 2 Outputs (Found branch, Miss branch)
        self.add_input_socket(name="In")
        self.socket_success = self.add_output_socket(
            name="Found", color=QColor(16, 185, 129)  # Green
        )
        self.socket_fail = self.add_output_socket(
            name="Miss", color=QColor(244, 63, 94)  # Rose red
        )
        self.socket_found = self.socket_success
        self.socket_miss = self.socket_fail

    def _load_thumbnail(self):
        tmpl = self.properties.get("template", "")
        raw_paths = [p.strip() for p in str(tmpl).split(";") if p.strip()]
        valid_paths = [p for p in raw_paths if os.path.exists(p)]
        if not valid_paths:
            self.thumbnail_pixmap = None
            return

        if len(valid_paths) == 1:
            pix = QPixmap(valid_paths[0])
            if not pix.isNull():
                self.thumbnail_pixmap = pix.scaled(
                    120, 44, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            else:
                self.thumbnail_pixmap = None
        else:
            # Composite thumbnail for multi-image OR variants
            comp_w = 126
            comp_h = 44
            composite = QPixmap(comp_w, comp_h)
            composite.fill(QColor(15, 23, 42))
            p = QPainter(composite)
            count = min(3, len(valid_paths))
            sub_w = comp_w // count
            for idx in range(count):
                sub_pix = QPixmap(valid_paths[idx])
                if not sub_pix.isNull():
                    scaled = sub_pix.scaled(
                        sub_w - 4, comp_h - 4, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                    sx = idx * sub_w + (sub_w - scaled.width()) // 2
                    sy = (comp_h - scaled.height()) // 2
                    p.drawPixmap(sx, sy, scaled)
                if idx < count - 1:
                    p.setPen(QColor(51, 65, 85))
                    p.drawLine((idx + 1) * sub_w, 4, (idx + 1) * sub_w, comp_h - 4)
            p.end()
            self.thumbnail_pixmap = composite

    def update_template(self, image_path: str, append: bool = False):
        if append:
            cur = str(self.properties.get("template", "")).strip()
            cur_list = [p.strip() for p in cur.split(";") if p.strip()]
            if image_path not in cur_list:
                cur_list.append(image_path)
            self.properties["template"] = ";".join(cur_list)
        else:
            self.properties["template"] = image_path
        self._load_thumbnail()
        self.update()

    def remove_template_variant(self, image_path: str):
        cur = str(self.properties.get("template", "")).strip()
        cur_list = [p.strip() for p in cur.split(";") if p.strip() and p.strip() != image_path]
        self.properties["template"] = ";".join(cur_list)
        self._load_thumbnail()
        self.update()

    def get_summary_text(self) -> str:
        conf = int(self.properties.get("confidence", 0.85) * 100)
        tout = float(self.properties.get("timeout", 5.0))
        tmpl = self.properties.get("template", "")
        n_tmpl = len([p.strip() for p in str(tmpl).split(";") if p.strip()])
        tmpl_info = f"{n_tmpl} Imgs (OR)" if n_tmpl > 1 else ""

        if self.properties.get("break_loop_on_found", False):
            extra = f" • {tmpl_info}" if tmpl_info else ""
            return f"🎯 Loop Until Found • {tout:g}s • ≥{conf}%{extra}"
        act = str(self.properties.get("action", "none")).capitalize()
        btn = str(self.properties.get("button", "left")).capitalize()
        act_str = f"{act} ({btn})" if act != "None" else "None"
        if tmpl_info:
            return f"Wait: {tout:g}s • ≥{conf}% • {tmpl_info}"
        return f"Wait: {tout:g}s  •  ≥{conf}%  •  {act_str}"

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)

        is_break = bool(self.properties.get("break_loop_on_found", False))
        if is_break:
            # Header Badge Pill for Loop Until Found
            badge_rect = QRectF(self.width - 95, 4, 90, 15)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(5, 150, 105)))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 6, QFont.Weight.Bold))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "🎯 Loop Until Found")

        # Draw thumbnail box
        thumb_rect = QRectF(16, self.header_height + 6, 130, 52)
        painter.setPen(QPen(QColor(51, 65, 85), 1))
        painter.setBrush(QBrush(QColor(15, 23, 42)))
        painter.drawRoundedRect(thumb_rect, 4, 4)

        if self.thumbnail_pixmap:
            # Center thumbnail inside box
            tx = thumb_rect.x() + (thumb_rect.width() - self.thumbnail_pixmap.width()) / 2
            ty = thumb_rect.y() + (thumb_rect.height() - self.thumbnail_pixmap.height()) / 2
            painter.drawPixmap(int(tx), int(ty), self.thumbnail_pixmap)
        else:
            painter.setPen(QColor(148, 163, 184))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Normal))
            painter.drawText(
                thumb_rect,
                Qt.AlignmentFlag.AlignCenter,
                "No template\n(Snip screen)",
            )

        # Label socket outputs
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(QColor(16, 185, 129))
        painter.drawText(
            QRectF(self.width - 65, self.header_height + 8, 55, 16),
            Qt.AlignmentFlag.AlignRight,
            "✓ Found →",
        )
        painter.setPen(QColor(244, 63, 94))
        painter.drawText(
            QRectF(self.width - 65, self.height - 24, 55, 16),
            Qt.AlignmentFlag.AlignRight,
            "✗ Miss →",
        )

    def clone(self) -> "VisionNodeItem":
        return VisionNodeItem(
            vision_type=self.node_type,
            properties=dict(self.properties),
        )


class IfConditionNodeItem(BaseNodeItem):
    """Conditional branching node: If Variable/Value compare with Operator."""

    def __init__(
        self,
        node_type: str = "if_condition",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="🔀 If / Compare",
            node_type="if_condition",
            color=QColor(245, 158, 11),  # Amber
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "if_condition")
        self.properties.setdefault("var_a", "$count")
        self.properties.setdefault("operator", "==")
        self.properties.setdefault("val_b", "5")
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 190.0
        self.height = 95.0

        # Sockets: 1 Input, 2 Outputs (True branch, False branch)
        self.add_input_socket(name="In")
        self.socket_true = self.add_output_socket(name="True", color=QColor(16, 185, 129))
        self.socket_false = self.add_output_socket(name="False", color=QColor(244, 63, 94))

    def get_summary_text(self) -> str:
        va = self.properties.get("var_a", "$var")
        op = self.properties.get("operator", "==")
        vb = self.properties.get("val_b", "")
        return f"If {va} {op} {vb}"

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        # Socket output labels
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(QColor(16, 185, 129))
        painter.drawText(
            QRectF(self.width - 55, self.header_height + 4, 45, 16),
            Qt.AlignmentFlag.AlignRight,
            "✓ True →",
        )
        painter.setPen(QColor(244, 63, 94))
        painter.drawText(
            QRectF(self.width - 55, self.height - 20, 45, 16),
            Qt.AlignmentFlag.AlignRight,
            "✗ False →",
        )

    def clone(self) -> "IfConditionNodeItem":
        return IfConditionNodeItem(properties=dict(self.properties))


class CompareNodeItem(BaseNodeItem):
    """Multi-condition logic & comparison node (AND / OR gates)."""

    def __init__(
        self,
        node_type: str = "compare",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="⚖ Compare / Logic",
            node_type="compare",
            color=QColor(139, 92, 246),  # Violet
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "compare")
        self.properties.setdefault("var_a", "$val1")
        self.properties.setdefault("op_a", "==")
        self.properties.setdefault("val_a", "1")
        self.properties.setdefault("logic_gate", "OR")
        self.properties.setdefault("enable_cond_b", True)
        self.properties.setdefault("var_b", "$val2")
        self.properties.setdefault("op_b", "==")
        self.properties.setdefault("val_b", "1")
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 205.0
        self.height = 100.0

        self.add_input_socket(name="In")
        self.socket_true = self.add_output_socket(name="True", color=QColor(16, 185, 129))
        self.socket_false = self.add_output_socket(name="False", color=QColor(244, 63, 94))

    def get_summary_text(self) -> str:
        va = self.properties.get("var_a", "$val1")
        oa = self.properties.get("op_a", "==")
        la = self.properties.get("val_a", "1")
        gate = self.properties.get("logic_gate", "OR")
        vb = self.properties.get("var_b", "$val2")
        ob = self.properties.get("op_b", "==")
        lb = self.properties.get("val_b", "1")
        if self.properties.get("enable_cond_b", True):
            return f"{va} {oa} {la}\n[{gate}] {vb} {ob} {lb}"
        return f"{va} {oa} {la}"

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(QColor(16, 185, 129))
        painter.drawText(
            QRectF(self.width - 55, self.header_height + 4, 45, 16),
            Qt.AlignmentFlag.AlignRight,
            "✓ True →",
        )
        painter.setPen(QColor(244, 63, 94))
        painter.drawText(
            QRectF(self.width - 55, self.height - 20, 45, 16),
            Qt.AlignmentFlag.AlignRight,
            "✗ False →",
        )

    def clone(self) -> "CompareNodeItem":
        return CompareNodeItem(properties=dict(self.properties))


class TimerNodeItem(BaseNodeItem):
    """Non-blocking timer and cooldown monitor node."""

    def __init__(
        self,
        node_type: str = "timer",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="⏱️ Timer / Cooldown",
            node_type="timer",
            color=QColor(20, 184, 166),  # Teal
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "timer")
        self.properties.setdefault("timer_name", "timer_1")
        self.properties.setdefault("mode", "check")  # "check", "reset", "read"
        self.properties.setdefault("threshold_ms", 3000)
        self.properties.setdefault("auto_reset", True)
        self.properties.setdefault("var_name", "elapsed_ms")
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 200.0
        self.height = 95.0

        self.add_input_socket(name="In")
        self.socket_true = self.add_output_socket(name="Elapsed", color=QColor(16, 185, 129))
        self.socket_false = self.add_output_socket(name="Waiting", color=QColor(245, 158, 11))
        self.socket_elapsed = self.socket_true
        self.socket_waiting = self.socket_false

    def get_summary_text(self) -> str:
        tname = self.properties.get("timer_name", "timer_1")
        mode = self.properties.get("mode", "check")
        if mode == "reset":
            return f"Reset '${tname}'\n(Set to 0s)"
        elif mode == "read":
            vn = self.properties.get("var_name", "elapsed_ms")
            return f"Read '${tname}'\n-> ${vn}"
        else:
            th = self.properties.get("threshold_ms", 3000)
            rst = " [Auto-Reset]" if self.properties.get("auto_reset", True) else ""
            return f"Timer '${tname}' >= {th}ms\n(Cooldown Check){rst}"

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        mode = self.properties.get("mode", "check")
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        if mode == "check":
            painter.setPen(QColor(16, 185, 129))
            painter.drawText(
                QRectF(self.width - 65, self.header_height + 4, 55, 16),
                Qt.AlignmentFlag.AlignRight,
                "⏱ Elapsed →",
            )
            painter.setPen(QColor(245, 158, 11))
            painter.drawText(
                QRectF(self.width - 65, self.height - 20, 55, 16),
                Qt.AlignmentFlag.AlignRight,
                "⏳ Waiting →",
            )
        else:
            painter.setPen(QColor(56, 189, 248))
            painter.drawText(
                QRectF(self.width - 55, int(self.height / 2), 45, 16),
                Qt.AlignmentFlag.AlignRight,
                "Out →",
            )

    def clone(self) -> "TimerNodeItem":
        return TimerNodeItem(properties=dict(self.properties))


class MathNodeItem(BaseNodeItem):
    """Math arithmetic & variable assignment node."""

    def __init__(
        self,
        node_type: str = "math_op",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="🔢 Math / Variable",
            node_type="math_op",
            color=QColor(20, 184, 166),  # Teal
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "math_op")
        self.properties.setdefault("var_name", "count")
        self.properties.setdefault("operation", "increment")
        self.properties.setdefault("value", "1")
        self.properties.setdefault("min_val", 100)
        self.properties.setdefault("max_val", 1000)
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 190.0
        self.height = 85.0

        self.add_input_socket(name="In")
        self.add_output_socket(name="Out")

    def get_summary_text(self) -> str:
        vn = self.properties.get("var_name", "var")
        op = self.properties.get("operation", "increment")
        val = self.properties.get("value", "1")
        if op == "increment":
            return f"${vn} += 1"
        elif op == "decrement":
            return f"${vn} -= 1"
        elif op == "set":
            return f"${vn} = {val}"
        elif op == "add":
            return f"${vn} += {val}"
        elif op == "subtract":
            return f"${vn} -= {val}"
        elif op == "multiply":
            return f"${vn} *= {val}"
        elif op == "random":
            mn = self.properties.get("min_val", 1)
            mx = self.properties.get("max_val", 100)
            return f"${vn} = rand({mn}..{mx})"
        return f"${vn} {op}"

    def clone(self) -> "MathNodeItem":
        return MathNodeItem(properties=dict(self.properties))


class PixelColorNodeItem(BaseNodeItem):
    """Pixel color matching node."""

    def __init__(
        self,
        node_type: str = "pixel_color",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="🎨 Pixel Color Check",
            node_type="pixel_color",
            color=QColor(217, 70, 239),  # Fuchsia
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "pixel_color")
        self.properties.setdefault("x", 500)
        self.properties.setdefault("y", 300)
        self.properties.setdefault("color", "#38BDF8")
        self.properties.setdefault("tolerance", 15)
        self.properties.setdefault("use_region", False)
        self.properties.setdefault("region_x", 500)
        self.properties.setdefault("region_y", 300)
        self.properties.setdefault("region_w", 100)
        self.properties.setdefault("region_h", 100)
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 195.0
        self.height = 95.0

        self.add_input_socket(name="In")
        self.socket_match = self.add_output_socket(name="Match", color=QColor(16, 185, 129))
        self.socket_mismatch = self.add_output_socket(name="Mismatch", color=QColor(244, 63, 94))

    def get_summary_text(self) -> str:
        col = self.properties.get("color", "#FFFFFF")
        tol = self.properties.get("tolerance", 15)
        if self.properties.get("use_region", False):
            rx = self.properties.get("region_x", self.properties.get("x", 0))
            ry = self.properties.get("region_y", self.properties.get("y", 0))
            rw = self.properties.get("region_w", 100)
            rh = self.properties.get("region_h", 100)
            return f"Box: ({rx}, {ry}) {rw}x{rh}\nColor: {col} (±{tol})"
        x = self.properties.get("x", 0)
        y = self.properties.get("y", 0)
        return f"Pos: ({x}, {y})\nColor: {col} (±{tol})"

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)

        # Draw mini color swatch
        col_hex = self.properties.get("color", "#FFFFFF")
        swatch_rect = QRectF(14, self.height - 22, 16, 14)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.setBrush(QBrush(QColor(col_hex)))
        painter.drawRoundedRect(swatch_rect, 2, 2)

        if self.properties.get("use_region", False):
            # Draw dashed bounding box icon indicator
            painter.setPen(QPen(QColor(217, 70, 239), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(34, self.height - 22, 16, 14))

        # Socket output labels
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(QColor(16, 185, 129))
        painter.drawText(
            QRectF(self.width - 60, self.header_height + 4, 50, 16),
            Qt.AlignmentFlag.AlignRight,
            "Match →",
        )
        painter.setPen(QColor(244, 63, 94))
        painter.drawText(
            QRectF(self.width - 60, self.height - 20, 50, 16),
            Qt.AlignmentFlag.AlignRight,
            "Miss →",
        )

    def clone(self) -> "PixelColorNodeItem":
        return PixelColorNodeItem(properties=dict(self.properties))


class HotkeyNodeItem(BaseNodeItem):
    """Multi-key keyboard combination node."""

    def __init__(
        self,
        node_type: str = "hotkey",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="⌨ Key Combination",
            node_type="hotkey",
            color=QColor(139, 92, 246),  # Violet
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "hotkey")
        self.properties.setdefault("combo", "Ctrl+C")
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 180.0
        self.height = 80.0

        self.add_input_socket(name="In")
        self.add_output_socket(name="Out")

    def get_summary_text(self) -> str:
        return f"Press:\n{self.properties.get('combo', 'Ctrl+C')}"

    def clone(self) -> "HotkeyNodeItem":
        return HotkeyNodeItem(properties=dict(self.properties))


class LoopNodeItem(BaseNodeItem):
    """Loop repeat zone node (Lego Mindstorms-style C-Clamp Bracket)."""

    def __init__(
        self,
        node_type: str = "loop_count",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="🔁 Repeat Zone (Loop)",
            node_type="loop_count",
            color=QColor(99, 102, 241),  # Indigo
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "loop_count")
        self.properties.setdefault("infinite", True)  # Default: Infinite!
        self.properties.setdefault("count", 5)
        self.properties.setdefault("var_name", "i")
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.clamp_width = 240.0
        self.clamp_height = 125.0
        self.spine_width = 38.0
        self.shelf_height = 26.0
        self.header_height = 28.0

        self.width = self.clamp_width
        self.height = self.clamp_height

        self.socket_in = self.add_input_socket(name="In", color=QColor(56, 189, 248))
        self.socket_repeat = self.add_input_socket(name="Loop In", color=QColor(168, 85, 247))
        self.socket_body = self.add_output_socket(name="Body", color=QColor(16, 185, 129))
        self.socket_done = self.add_output_socket(name="Done", color=QColor(6, 182, 212))

        # Position Loop behind regular action nodes so body actions sit visibly in mouth
        self.setZValue(0.1)
        self._layout_sockets()

    def get_body_nodes(self) -> List["BaseNodeItem"]:
        if not hasattr(self, "socket_body") or not self.socket_body.connections:
            return []
        nodes = []
        visited = {self}
        queue = []
        for conn in self.socket_body.connections:
            if conn.end_socket and conn.end_socket.node and conn.end_socket.node != self:
                queue.append(conn.end_socket.node)
        while queue:
            curr = queue.pop(0)
            if curr in visited or curr == self:
                continue
            visited.add(curr)
            nodes.append(curr)

            # If curr is a nested LoopNodeItem, its internal body nodes belong to curr's own jaw.
            # Do NOT traverse into curr's socket_body; only follow curr's socket_done to continue
            # traversing subsequent nodes at OUR loop level.
            if isinstance(curr, LoopNodeItem):
                out_sockets = [curr.socket_done] if hasattr(curr, "socket_done") else []
            else:
                out_sockets = curr.output_sockets

            for out_sock in out_sockets:
                for c in out_sock.connections:
                    if c.end_socket and c.end_socket.node:
                        target = c.end_socket.node
                        if target not in visited and target != self:
                            queue.append(target)
        return nodes

    def update_clamp_bounds(self):
        body_nodes = self.get_body_nodes()
        if not body_nodes:
            new_w = 240.0
            new_h = 125.0
        else:
            my_x = self.pos().x()
            my_y = self.pos().y()
            max_x = max(n.pos().x() + n.width for n in body_nodes)
            max_y = max(n.pos().y() + n.height for n in body_nodes)
            new_w = max(240.0, (max_x - my_x) + 40.0)
            new_h = max(125.0, (max_y - my_y) + 45.0)

        if abs(new_w - self.clamp_width) > 1.0 or abs(new_h - self.clamp_height) > 1.0:
            self.prepareGeometryChange()
            self.clamp_width = new_w
            self.clamp_height = new_h
            self.width = new_w
            self.height = new_h
            self._layout_sockets()
            self.update()

    def _layout_sockets(self):
        if not hasattr(self, "socket_in") or not hasattr(self, "socket_done"):
            return
        # 1. socket_in: Left outside spine
        self.socket_in.setPos(0, 48.0)
        # 2. socket_repeat: Left outside near bottom shelf (for backward wires)
        self.socket_repeat.setPos(0, self.clamp_height - 13.0)
        # 3. socket_body: Inner edge of left spine pointing directly into the mouth!
        self.socket_body.setPos(self.spine_width, 48.0)
        # 4. socket_done: Right end of the bottom shelf!
        self.socket_done.setPos(self.clamp_width, self.clamp_height - 13.0)

    def boundingRect(self) -> QRectF:
        return QRectF(-10, -10, self.clamp_width + 20, self.clamp_height + 20)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            new_pos = value
            old_pos = self.pos()
            delta = new_pos - old_pos
            if not getattr(self, "_in_body_sync", False):
                self._in_body_sync = True
                for b_node in self.get_body_nodes():
                    # Only move nodes that are not already being moved by Qt's selection drag
                    if not b_node.isSelected():
                        b_node.setPos(b_node.pos() + delta)
                        b_node.update_connected_wires()
                self._in_body_sync = False
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.update_connected_wires()
        return super().itemChange(change, value)

    def get_summary_text(self) -> str:
        is_inf = bool(self.properties.get("infinite", True))
        vn = self.properties.get("var_name", "i")
        if is_inf:
            return f"Mode: ∞ Infinite\n(Index: ${vn})"
        cnt = self.properties.get("count", 5)
        return f"Repeat {cnt} times\n(Index: ${vn})"

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.clamp_width
        h = self.clamp_height
        sp_w = self.spine_width
        sh_h = self.shelf_height
        hdr_h = self.header_height

        is_sel = self.isSelected()
        is_inf = bool(self.properties.get("infinite", True))
        cnt = self.properties.get("count", 5)

        # 1. Translucent Mouth / Container Interior Backdrop
        mouth_rect = QRectF(sp_w, hdr_h, w - sp_w, h - hdr_h - sh_h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(99, 102, 241, 18)))  # Soft indigo glow
        painter.drawRect(mouth_rect)

        # Dashed border along mouth
        dash_pen = QPen(QColor(99, 102, 241, 90), 1.5, Qt.PenStyle.DashLine)
        painter.setPen(dash_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(mouth_rect)

        # 2. Solid C-Clamp Structural Spine, Header, and Bottom Shelf
        bracket_path = QPainterPath()
        bracket_path.moveTo(0, 8)
        bracket_path.quadTo(0, 0, 8, 0)
        bracket_path.lineTo(w - 8, 0)
        bracket_path.quadTo(w, 0, w, 8)
        bracket_path.lineTo(w, hdr_h)
        bracket_path.lineTo(sp_w, hdr_h)
        bracket_path.lineTo(sp_w, h - sh_h)
        bracket_path.lineTo(w, h - sh_h)
        bracket_path.lineTo(w, h - 8)
        bracket_path.quadTo(w, h, w - 8, h)
        bracket_path.lineTo(8, h)
        bracket_path.quadTo(0, h, 0, h - 8)
        bracket_path.closeSubpath()

        # Fill bracket body
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 41, 59)))  # Dark slate
        painter.drawPath(bracket_path)

        # Top arm header fill
        hdr_path = QPainterPath()
        hdr_path.moveTo(0, 8)
        hdr_path.quadTo(0, 0, 8, 0)
        hdr_path.lineTo(w - 8, 0)
        hdr_path.quadTo(w, 0, w, 8)
        hdr_path.lineTo(w, hdr_h)
        hdr_path.lineTo(0, hdr_h)
        hdr_path.closeSubpath()
        painter.setBrush(QBrush(QColor(79, 70, 229)))  # Vibrant Indigo
        painter.drawPath(hdr_path)

        # Bracket outer border
        if getattr(self, "is_executing", False):
            glow_pen = QPen(QColor(16, 185, 129, 120), 7.0)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(bracket_path)
            border_pen = QPen(QColor(16, 185, 129), 3.2)
        elif is_sel:
            border_pen = QPen(QColor(251, 146, 60), 2.0)
        else:
            border_pen = QPen(QColor(99, 102, 241), 1.5)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(bracket_path)

        # Header Title & Icons
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(10, 0, 160, hdr_h), Qt.AlignmentFlag.AlignVCenter, "🔁 REPEAT ZONE")

        # Executing Running Badge
        if getattr(self, "is_executing", False):
            run_badge_rect = QRectF(w - 180, 5, 62, 18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(16, 185, 129)))
            painter.drawRoundedRect(run_badge_rect, 4, 4)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.drawText(run_badge_rect, Qt.AlignmentFlag.AlignCenter, "⚡ RUNNING")

        # Badge: [∞ Infinite] vs [Count]
        badge_text = "∞ Infinite" if is_inf else f"{cnt}x"
        badge_w = 60 if is_inf else 34
        badge_rect = QRectF(w - badge_w - 55, 5, badge_w, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        badge_col = QColor(67, 56, 202) if is_inf else QColor(51, 65, 85)
        painter.setBrush(QBrush(badge_col))
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Index variable display
        vn = self.properties.get("var_name", "i")
        painter.setPen(QColor(199, 210, 254))
        painter.drawText(QRectF(w - 50, 0, 42, hdr_h), Qt.AlignmentFlag.AlignVCenter, f"${vn}")

        # Socket text labels
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))

        # 1. Left input socket labels
        painter.setPen(QColor(56, 189, 248))
        painter.drawText(QRectF(6, 40, 28, 16), Qt.AlignmentFlag.AlignLeft, "In")

        # 2. Right output socket labels
        painter.setPen(QColor(16, 185, 129))
        painter.drawText(QRectF(sp_w + 6, 40, 50, 16), Qt.AlignmentFlag.AlignLeft, "Body →")

        # 3. Bottom shelf auto-cycle hint
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Normal))
        painter.setPen(QColor(165, 180, 252))
        painter.drawText(
            QRectF(sp_w + 10, h - sh_h, w - sp_w - 65, sh_h),
            Qt.AlignmentFlag.AlignVCenter,
            "⤴ Auto-cycles body sequence",
        )

        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(QColor(6, 182, 212))
        painter.drawText(
            QRectF(w - 60, h - sh_h, 50, sh_h),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "Done →",
        )

    def clone(self) -> "LoopNodeItem":
        return LoopNodeItem(properties=dict(self.properties))


class StopNodeItem(BaseNodeItem):
    """Explicitly stops macro playback."""

    def __init__(
        self,
        node_type: str = "stop_playback",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="⏹ Stop Playback",
            node_type="stop_playback",
            color=QColor(239, 68, 68),  # Red
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "stop_playback")
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 150.0
        self.height = 65.0

        self.add_input_socket(name="In")

    def get_summary_text(self) -> str:
        return "Halt playback"

    def clone(self) -> "StopNodeItem":
        return StopNodeItem(properties=dict(self.properties))


class AIVisionNodeItem(BaseNodeItem):
    """Multimodal AI Vision & Action Agent node (recreates multi-step actions with visual reasoning)."""

    def __init__(
        self,
        node_type: str = "ai_vision",
        properties: Optional[Dict[str, Any]] = None,
        parent=None,
    ):
        super().__init__(
            title="🤖 AI Vision Action",
            node_type="ai_vision",
            color=QColor(168, 85, 247),  # Vibrant Purple
            parent=parent,
        )
        self.properties = properties or {}
        self.properties.setdefault("action_type", "ai_vision")
        self.properties.setdefault("prompt", "Find and click target element")
        self.properties.setdefault("mode", "multi_step")
        self.properties.setdefault("server_url", "http://localhost:11434/v1")
        self.properties.setdefault("model_name", "ui-tars-7b")
        self.properties.setdefault("max_steps", 5)
        self.properties.setdefault("step_delay_ms", 300)
        self.properties.setdefault("region_mode", "fullscreen")
        self.properties.setdefault("region_x", 0)
        self.properties.setdefault("region_y", 0)
        self.properties.setdefault("region_w", 800)
        self.properties.setdefault("region_h", 600)
        self.properties.setdefault("mock_fallback", True)
        if "bypassed" in self.properties:
            self.bypassed = bool(self.properties["bypassed"])

        self.width = 220.0
        self.height = 95.0

        self.add_input_socket(name="In")
        self.socket_success = self.add_output_socket(name="Success", color=QColor(16, 185, 129))
        self.socket_fail = self.add_output_socket(name="Fail", color=QColor(244, 63, 94))

    def get_summary_text(self) -> str:
        prompt = str(self.properties.get("prompt", "AI Action"))
        mode = str(self.properties.get("mode", "multi_step")).replace("_", " ").title()
        max_s = self.properties.get("max_steps", 5)
        if len(prompt) > 28:
            prompt = prompt[:25] + "..."
        if mode.lower() == "multi step":
            return f"[{mode} ({max_s} max)]\n\"{prompt}\""
        return f"[{mode}]\n\"{prompt}\""

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(QColor(16, 185, 129))
        painter.drawText(
            QRectF(self.width - 65, self.header_height + 4, 55, 16),
            Qt.AlignmentFlag.AlignRight,
            "✓ Success →",
        )
        painter.setPen(QColor(244, 63, 94))
        painter.drawText(
            QRectF(self.width - 65, self.height - 20, 55, 16),
            Qt.AlignmentFlag.AlignRight,
            "✗ Fail →",
        )

    def clone(self) -> "AIVisionNodeItem":
        return AIVisionNodeItem(properties=dict(self.properties))

