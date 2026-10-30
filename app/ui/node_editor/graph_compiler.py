"""Compiler and converter between recorded macro step lists and node graphs."""

from __future__ import annotations

import copy
from typing import List, Dict, Any, Optional, Tuple
from PyQt6.QtCore import QPointF

from app.ui.node_editor.node_scene import NodeScene
from app.ui.node_editor.node_items import (
    BaseNodeItem,
    StartNodeItem,
    ActionNodeItem,
    VisionNodeItem,
    IfConditionNodeItem,
    CompareNodeItem,
    TimerNodeItem,
    MathNodeItem,
    PixelColorNodeItem,
    HotkeyNodeItem,
    LoopNodeItem,
    StopNodeItem,
)
from app.ui.node_editor.node_socket import NodeSocketItem


def macro_to_graph(
    steps: List[Dict[str, Any]], scene: NodeScene, default_direct_move: bool = True
):
    """Converts a recorded macro steps list into an interactive left-to-right node graph."""
    scene.clear()
    scene.nodes.clear()
    scene.connections.clear()
    scene.groups.clear()

    # 1. Add Entry Start Node
    start_node = StartNodeItem()
    scene.add_node(start_node, QPointF(60, 200))

    prev_node: BaseNodeItem = start_node
    curr_x = 240.0
    curr_y = 200.0

    # If steps are empty, we're done
    if not steps:
        return

    # Smart compacting of recorded macro steps:
    # 1. Collapse paired mouse down + up into clean Click or Double Click nodes
    # 2. Collapse consecutive micro moves into endpoint moves while storing full trajectory
    compacted_steps = []
    i = 0
    n = len(steps)

    while i < n:
        step = steps[i]
        st_type = step.get("type", "click")

        # Check if down followed closely by up on same button is a click
        if st_type == "down" and (i + 1 < n) and steps[i + 1].get("type") == "up":
            next_step = steps[i + 1]
            if step.get("button", "left") == next_step.get("button", "left"):
                is_dbl = next_step.get("is_dblclick", False)
                click_type = "dblclick" if is_dbl else "click"
                click_step = {
                    "type": click_type,
                    "x": step.get("x", next_step.get("x", 0)),
                    "y": step.get("y", next_step.get("y", 0)),
                    "button": step.get("button", "left"),
                    "dt": step.get("dt", 0),
                }
                compacted_steps.append(click_step)
                i += 2
                continue

        # Consecutive move stream: collapse to single move node while retaining trajectory points
        if st_type == "move":
            path = []
            if "path_points" in step and step["path_points"]:
                path.extend(step["path_points"])
            else:
                path.append(step)

            direct_jump = step.get("direct_jump", default_direct_move)

            while (i + 1 < n) and steps[i + 1].get("type") == "move":
                i += 1
                next_step = steps[i]
                if "path_points" in next_step and next_step["path_points"]:
                    path.extend(next_step["path_points"])
                else:
                    path.append(next_step)
                if "direct_jump" in next_step:
                    direct_jump = next_step["direct_jump"]

            last_m = copy.deepcopy(path[-1])
            last_m["type"] = "move"
            last_m["path_points"] = path
            last_m["direct_jump"] = direct_jump
            compacted_steps.append(last_m)
            i += 1
            continue

        compacted_steps.append(step)
        i += 1

    # Cap visual nodes to a reasonable maximum (e.g. 150) to keep graph fast and readable
    rendered_steps = compacted_steps[:150]
    has_branching = any("found_next" in s or "miss_next" in s for s in rendered_steps)
    node_id_map: Dict[str, BaseNodeItem] = {}
    created_nodes: List[Tuple[Dict[str, Any], BaseNodeItem]] = []

    for i, step in enumerate(rendered_steps):
        st_type = step.get("type", "click")

        node: BaseNodeItem
        if st_type in ("find_image", "wait_image", "wait", "waitforimage"):
            node = VisionNodeItem(vision_type="wait_image", properties=step)
        elif st_type == "if_condition":
            node = IfConditionNodeItem(properties=step)
        elif st_type == "compare":
            node = CompareNodeItem(properties=step)
        elif st_type == "timer":
            node = TimerNodeItem(properties=step)
        elif st_type == "math_op":
            node = MathNodeItem(properties=step)
        elif st_type == "pixel_color":
            node = PixelColorNodeItem(properties=step)
        elif st_type == "hotkey":
            node = HotkeyNodeItem(properties=step)
        elif st_type == "loop_count":
            node = LoopNodeItem(properties=step)
        elif st_type == "stop_playback":
            node = StopNodeItem(properties=step)
        else:
            node = ActionNodeItem(action_type=st_type, properties=step)

        # Preserve ID if present
        if step.get("id"):
            node.id = step["id"]
            node_id_map[str(step["id"])] = node

        if step.get("bypassed", False):
            node.set_bypassed(True)

        # Place left-to-right
        node_pos = QPointF(curr_x, curr_y)
        scene.add_node(node, node_pos)
        created_nodes.append((step, node))

        # If not branching, connect previous node's output to this node's input unless step was unplugged
        if not has_branching:
            if not step.get("_unplugged", False):
                if prev_node and prev_node.output_sockets and node.input_sockets:
                    s_idx = int(step.get("_socket_idx", 0))
                    if s_idx >= len(prev_node.output_sockets):
                        s_idx = 0
                    out_sock = prev_node.output_sockets[s_idx]
                    in_sock = node.input_sockets[0]
                    scene.add_connection(out_sock, in_sock)
                prev_node = node

        curr_x += node.width + 50.0

    # If branching, wire connections based on target IDs
    if has_branching and created_nodes:
        # Connect Start node to first node
        first_step, first_node = created_nodes[0]
        if start_node.output_sockets and first_node.input_sockets:
            scene.add_connection(start_node.output_sockets[0], first_node.input_sockets[0])

        for step, node in created_nodes:
            if step.get("_unplugged", False):
                continue

            # Loop Body socket (index 0)
            if "body_next" in step:
                b_id = step.get("body_next")
                if b_id and b_id in node_id_map:
                    target_node = node_id_map[b_id]
                    if len(node.output_sockets) > 0 and len(target_node.input_sockets) > 0:
                        scene.add_connection(node.output_sockets[0], target_node.input_sockets[0])

            # Found socket (index 0)
            if "found_next" in step:
                f_id = step.get("found_next")
                if f_id and f_id in node_id_map:
                    target_node = node_id_map[f_id]
                    if len(node.output_sockets) > 0 and len(target_node.input_sockets) > 0:
                        scene.add_connection(node.output_sockets[0], target_node.input_sockets[0])

            # Miss socket (index 1)
            if "miss_next" in step:
                m_id = step.get("miss_next")
                if m_id and m_id in node_id_map:
                    target_node = node_id_map[m_id]
                    if len(node.output_sockets) > 1 and len(target_node.input_sockets) > 0:
                        scene.add_connection(node.output_sockets[1], target_node.input_sockets[0])

            # Standard next socket (for LoopNodeItem, 'next' is index 1 Done; for others, index 0)
            if "next" in step:
                n_id = step.get("next")
                if n_id and n_id in node_id_map:
                    target_node = node_id_map[n_id]
                    out_idx = 1 if isinstance(node, LoopNodeItem) else 0
                    in_idx = 0
                    if isinstance(target_node, LoopNodeItem) and len(target_node.input_sockets) > 1:
                        if target_node.input_sockets[0].connections:
                            in_idx = 1
                    if len(node.output_sockets) > out_idx and len(target_node.input_sockets) > in_idx:
                        scene.add_connection(node.output_sockets[out_idx], target_node.input_sockets[in_idx])

    if hasattr(scene, "update_loop_bounds"):
        scene.update_loop_bounds()


def graph_to_macro(scene: NodeScene) -> List[Dict[str, Any]]:
    """Traverses the graph starting from StartNodeItem and compiles into macro steps."""
    # Find Start node
    start_node = next((n for n in scene.nodes if isinstance(n, StartNodeItem)), None)
    if not start_node:
        return []

    compiled_steps: List[Dict[str, Any]] = []
    visited = set()
    current_dt = 0

    # Auto-cycle detection: For any LoopNodeItem, map the end of its body chain back to the loop
    # so users don't need to manually draw an ugly backward wire across their canvas!
    auto_cycle_map: Dict[str, str] = {}
    for n in scene.nodes:
        if isinstance(n, LoopNodeItem):
            lid = getattr(n, "id", None) or hex(id(n))
            if n.output_sockets and n.output_sockets[0].connections:
                body_start = n.output_sockets[0].connections[0].end_socket.node
                curr = body_start
                visited_chain = set()
                while curr and curr != n and curr not in visited_chain:
                    visited_chain.add(curr)
                    if curr.output_sockets and curr.output_sockets[0].connections:
                        nxt = curr.output_sockets[0].connections[0].end_socket.node
                        if nxt == n or nxt in visited_chain:
                            break
                        curr = nxt
                    else:
                        auto_cycle_map[getattr(curr, "id", None) or hex(id(curr))] = lid
                        break

    # Queue of nodes to process in graph traversal order
    def get_next_nodes(node: BaseNodeItem) -> List[BaseNodeItem]:
        next_nodes = []
        for out_sock in node.output_sockets:
            for conn in out_sock.connections:
                if conn.end_socket and conn.end_socket.node:
                    dst = conn.end_socket.node
                    if dst not in visited:
                        next_nodes.append(dst)
        return next_nodes

    curr_node = start_node
    queue: List[BaseNodeItem] = get_next_nodes(curr_node)

    while queue:
        node = queue.pop(0)
        if node in visited:
            continue
        visited.add(node)

        # Convert node properties to step dict
        props = dict(node.properties)
        action_type = props.get("action_type", node.node_type)
        node_id = getattr(node, "id", None) or hex(id(node))

        # Helper to get target node id for a socket index
        def get_target_id(sock_idx: int) -> Optional[str]:
            if sock_idx < len(node.output_sockets) and node.output_sockets[sock_idx].connections:
                conn = node.output_sockets[sock_idx].connections[0]
                if conn.end_socket and conn.end_socket.node:
                    return getattr(conn.end_socket.node, "id", None) or hex(id(conn.end_socket.node))
            return None

        step: Dict[str, Any] = {"id": node_id, "type": action_type}
        if getattr(node, "bypassed", False):
            step["bypassed"] = True

        if isinstance(node, VisionNodeItem):
            step["type"] = "wait_image"
            step["template"] = props.get("template", "")
            step["confidence"] = float(props.get("confidence", 0.85))
            step["action"] = props.get("action", "none")
            step["button"] = props.get("button", "left")
            step["timeout"] = float(props.get("timeout", 5.0))
            is_break = bool(props.get("break_loop_on_found", False))
            step["break_loop_on_found"] = is_break
            f_next = get_target_id(0)
            m_next = get_target_id(1)

            # Auto-route if break_loop_on_found is active inside a loop:
            if is_break and node_id in auto_cycle_map:
                parent_lid = auto_cycle_map[node_id]
                # If found_next not explicitly wired, route to loop's Done target
                if not f_next:
                    for s_node in scene.nodes:
                        if isinstance(s_node, LoopNodeItem) and (getattr(s_node, "id", None) or hex(id(s_node))) == parent_lid:
                            if s_node.output_sockets and len(s_node.output_sockets) > 1 and s_node.output_sockets[1].connections:
                                end_n = s_node.output_sockets[1].connections[0].end_socket.node
                                if end_n:
                                    f_next = getattr(end_n, "id", None) or hex(id(end_n))
                            break
                # If miss_next not explicitly wired, cycle back to loop
                if not m_next:
                    m_next = parent_lid

            step["found_next"] = f_next
            step["miss_next"] = m_next
            current_dt += 150
            step["dt"] = current_dt

        elif isinstance(node, ActionNodeItem):
            step["type"] = action_type
            step["next"] = get_target_id(0)

            if action_type == "move":
                direct_jump = bool(props.get("direct_jump", True))
                path_points = props.get("path_points", [])
                raw_x = props.get("x", 0)
                raw_y = props.get("y", 0)
                try:
                    target_x = int(raw_x)
                except (ValueError, TypeError):
                    target_x = str(raw_x)
                try:
                    target_y = int(raw_y)
                except (ValueError, TypeError):
                    target_y = str(raw_y)

                if direct_jump or not path_points or len(path_points) <= 1:
                    current_dt += 50
                    step["x"] = target_x
                    step["y"] = target_y
                    step["button"] = props.get("button", "left")
                    step["direct_jump"] = True
                    if path_points:
                        step["path_points"] = path_points
                    step["dt"] = current_dt
                    compiled_steps.append(step)
                else:
                    first_pt_dt = path_points[0].get("dt", 0)
                    next_node_id = get_target_id(0)
                    sub_ids = [f"{node_id}_p{k}" for k in range(len(path_points))]
                    for idx, pt in enumerate(path_points):
                        pt_step = copy.deepcopy(pt)
                        pt_step["id"] = sub_ids[idx]
                        pt_step["type"] = "move"
                        if idx < len(path_points) - 1:
                            pt_step["next"] = sub_ids[idx + 1]
                        else:
                            pt_step["x"] = target_x
                            pt_step["y"] = target_y
                            pt_step["direct_jump"] = False
                            pt_step["path_points"] = path_points
                            pt_step["next"] = next_node_id
                        pt_dt_offset = max(0, pt.get("dt", 0) - first_pt_dt)
                        pt_step["dt"] = current_dt + pt_dt_offset
                        compiled_steps.append(pt_step)
                    traj_duration = max(50, path_points[-1].get("dt", 0) - first_pt_dt)
                    current_dt += traj_duration
                # Continue loop to enqueue connected outgoing nodes
                for next_node in get_next_nodes(node):
                    if next_node not in visited and next_node not in queue:
                        queue.append(next_node)
                continue

            elif action_type in ("click", "dblclick", "down", "up"):
                raw_x = props.get("x", 0)
                raw_y = props.get("y", 0)
                try:
                    step["x"] = int(raw_x)
                except (ValueError, TypeError):
                    step["x"] = str(raw_x)
                try:
                    step["y"] = int(raw_y)
                except (ValueError, TypeError):
                    step["y"] = str(raw_y)
                step["button"] = props.get("button", "left")
                current_dt += 100
                step["dt"] = current_dt

            elif action_type == "delay":
                raw_dur = props.get("duration", 500)
                try:
                    dur = int(raw_dur)
                    current_dt += dur
                except (ValueError, TypeError):
                    dur = str(raw_dur)
                    current_dt += 100
                step["duration"] = dur
                step["dt"] = current_dt

            elif action_type == "type":
                step["value"] = props.get("value", "")
                current_dt += 120
                step["dt"] = current_dt

            elif action_type in ("key_press", "key_down", "key_up", "key"):
                key_name = props.get("key", "")
                if key_name:
                    step["key"] = key_name
                try:
                    step["vk"] = int(props.get("vk", 0)) if props.get("vk") else 0
                except (ValueError, TypeError):
                    step["vk"] = 0
                if action_type == "key_down":
                    step["hold_duration"] = props.get("hold_duration", 0)
                    step["auto_repeat"] = bool(props.get("auto_repeat", True))
                current_dt += 50
                step["dt"] = current_dt

            elif action_type == "wheel":
                raw_dy = props.get("deltaY", 0)
                try:
                    step["deltaY"] = int(raw_dy)
                except (ValueError, TypeError):
                    step["deltaY"] = str(raw_dy)
                raw_dx = props.get("deltaX", 0)
                try:
                    step["deltaX"] = int(raw_dx)
                except (ValueError, TypeError):
                    step["deltaX"] = str(raw_dx)
                if "x" in props and "y" in props:
                    raw_x = props["x"]
                    raw_y = props["y"]
                    try:
                        step["x"] = int(raw_x)
                    except (ValueError, TypeError):
                        step["x"] = str(raw_x)
                    try:
                        step["y"] = int(raw_y)
                    except (ValueError, TypeError):
                        step["y"] = str(raw_y)
                current_dt += 80
                step["dt"] = current_dt

        elif isinstance(node, IfConditionNodeItem):
            step["type"] = "if_condition"
            step["var_a"] = props.get("var_a", "$count")
            step["operator"] = props.get("operator", "==")
            step["val_b"] = props.get("val_b", "5")
            step["found_next"] = get_target_id(0)
            step["miss_next"] = get_target_id(1)
            current_dt += 10
            step["dt"] = current_dt

        elif isinstance(node, CompareNodeItem):
            step["type"] = "compare"
            step["var_a"] = props.get("var_a", "$val1")
            step["op_a"] = props.get("op_a", "==")
            step["val_a"] = props.get("val_a", "1")
            step["logic_gate"] = props.get("logic_gate", "OR")
            step["enable_cond_b"] = bool(props.get("enable_cond_b", True))
            step["var_b"] = props.get("var_b", "$val2")
            step["op_b"] = props.get("op_b", "==")
            step["val_b"] = props.get("val_b", "1")
            step["found_next"] = get_target_id(0)
            step["miss_next"] = get_target_id(1)
            current_dt += 10
            step["dt"] = current_dt

        elif isinstance(node, TimerNodeItem):
            step["type"] = "timer"
            step["timer_name"] = props.get("timer_name", "timer_1")
            t_mode = props.get("mode", "check")
            step["mode"] = t_mode
            step["threshold_ms"] = props.get("threshold_ms", 3000)
            step["auto_reset"] = bool(props.get("auto_reset", True))
            step["var_name"] = props.get("var_name", "elapsed_ms")
            if t_mode == "check":
                step["found_next"] = get_target_id(0)
                step["miss_next"] = get_target_id(1)
            else:
                step["next"] = get_target_id(0)
            current_dt += 10
            step["dt"] = current_dt

        elif isinstance(node, MathNodeItem):
            step["type"] = "math_op"
            step["var_name"] = props.get("var_name", "count")
            step["operation"] = props.get("operation", "increment")
            step["value"] = props.get("value", "1")
            step["min_val"] = props.get("min_val", 100)
            step["max_val"] = props.get("max_val", 1000)
            step["next"] = get_target_id(0)
            current_dt += 10
            step["dt"] = current_dt

        elif isinstance(node, PixelColorNodeItem):
            step["type"] = "pixel_color"
            raw_x = props.get("x", 0)
            raw_y = props.get("y", 0)
            try:
                step["x"] = int(raw_x)
            except (ValueError, TypeError):
                step["x"] = str(raw_x)
            try:
                step["y"] = int(raw_y)
            except (ValueError, TypeError):
                step["y"] = str(raw_y)
            step["color"] = props.get("color", "#FFFFFF")
            try:
                step["tolerance"] = int(props.get("tolerance", 15))
            except (ValueError, TypeError):
                step["tolerance"] = str(props.get("tolerance", 15))
            use_reg = bool(props.get("use_region", False))
            step["use_region"] = use_reg
            if use_reg:
                raw_rx = props.get("region_x", raw_x)
                raw_ry = props.get("region_y", raw_y)
                raw_rw = props.get("region_w", 100)
                raw_rh = props.get("region_h", 100)
                try:
                    step["region_x"] = int(raw_rx)
                except (ValueError, TypeError):
                    step["region_x"] = str(raw_rx)
                try:
                    step["region_y"] = int(raw_ry)
                except (ValueError, TypeError):
                    step["region_y"] = str(raw_ry)
                try:
                    step["region_w"] = int(raw_rw)
                except (ValueError, TypeError):
                    step["region_w"] = str(raw_rw)
                try:
                    step["region_h"] = int(raw_rh)
                except (ValueError, TypeError):
                    step["region_h"] = str(raw_rh)
            step["found_next"] = get_target_id(0)
            step["miss_next"] = get_target_id(1)
            current_dt += 20
            step["dt"] = current_dt

        elif isinstance(node, HotkeyNodeItem):
            step["type"] = "hotkey"
            step["combo"] = props.get("combo", "Ctrl+C")
            step["cad_action"] = props.get("cad_action", "taskmgr")
            step["next"] = get_target_id(0)
            current_dt += 100
            step["dt"] = current_dt

        elif isinstance(node, LoopNodeItem):
            step["type"] = "loop_count"
            raw_count = props.get("count", 5)
            try:
                step["count"] = int(raw_count)
            except (ValueError, TypeError):
                step["count"] = str(raw_count)
            step["infinite"] = bool(props.get("infinite", True))
            step["var_name"] = props.get("var_name", "i")
            step["body_next"] = get_target_id(0)
            step["next"] = get_target_id(1)
            current_dt += 10
            step["dt"] = current_dt

        elif isinstance(node, StopNodeItem):
            step["type"] = "stop_playback"
            current_dt += 10
            step["dt"] = current_dt

        # If a step is inside a loop body and has no explicit next connection, auto-cycle back!
        if step.get("next") is None and node_id in auto_cycle_map:
            step["next"] = auto_cycle_map[node_id]

        compiled_steps.append(step)

        # Enqueue connected outgoing nodes
        for next_node in get_next_nodes(node):
            if next_node not in visited and next_node not in queue:
                queue.append(next_node)

    return compiled_steps
