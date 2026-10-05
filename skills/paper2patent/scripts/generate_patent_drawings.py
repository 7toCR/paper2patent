#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate black-and-white Chinese patent drawings (SVG + PNG) from JSON.

Input: the patent content JSON. Each entry of `drawings` is a structured
figure spec with explicit nodes and edges (see references/drawing-generation.md):

    {"figure_no": 1, "title": "……方法的流程示意图", "type": "flowchart",
     "nodes": [{"id": "S101", "label": "S101 获取待处理视频"},
               {"id": "S102", "label": "S102 ……", "shape": "decision"}],
     "edges": [{"from": "S101", "to": "S102"},
               {"from": "S102", "to": "S101", "label": "否"}],
     "source": "论文图2；第3.1节"}

Design rules enforced here:
- Only the nodes and edges listed are drawn. Nothing is inferred.
- Labels are wrapped, never truncated.
- No figure number or title is drawn inside the image (captions live in the
  document, as "图1" under the figure).
- Pure black lines on white; PNG rendered with a real CJK font or not at all.

Layout is a small layered (Sugiyama-style) layout: cycle removal, longest-path
layering, dummy nodes for long edges, barycentre ordering and separation-
constrained placement, then orthogonal edge routing through per-gap channels.

Standard library only; Pillow is needed for the PNG copies.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patent_common import (  # noqa: E402
    FIGURE_NO_RE,
    eprint,
    load_cjk_font,
    normalize_drawings,
    read_json,
    text_units,
    wrap_text,
    write_json,
)

FONT = 22
LINE_H = 30
PAD_X = 22
PAD_Y = 16
H_GAP = 56
DUMMY_GAP = 26
V_GAP_BASE = 56
CHANNEL_STEP = 16
MARGIN = 20
STROKE = 2
PNG_SCALE = 2
ARROW_LEN = 13
ARROW_HALF = 5.5
MAX_UNITS = {"flowchart": 18, "block": 12}
MIN_NODE_W = 180
PRINT_MAX_W_CM = 15.0  # must match generate_patent_docx.MAX_W_CM / MAX_H_CM
PRINT_MAX_H_CM = 20.0
MIN_TEXT_MM = 2.2  # ≈ 8 pt Chinese text after scaling onto the page
MAX_NODES_HINT = 16


class Node:
    def __init__(self, nid: str, label: str = "", shape: str = "process", ref: str | None = None,
                 dummy: bool = False, order_hint: int = 0) -> None:
        self.id = nid
        self.label = label
        self.shape = shape
        self.ref = ref
        self.dummy = dummy
        self.order_hint = order_hint
        self.lines: list[str] = []
        self.w = 0.0
        self.h = 0.0
        self.layer = 0
        self.x = 0.0  # centre
        self.y = 0.0  # top

    @property
    def ref_space(self) -> float:
        if not self.ref:
            return 0.0
        return 26 + text_units(self.ref) * FONT

    def half_left(self) -> float:
        return 6.0 if self.dummy else self.w / 2

    def half_right(self) -> float:
        return 6.0 if self.dummy else self.w / 2 + self.ref_space

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


class Segment:
    def __init__(self, upper: str, lower: str, edge_index: int) -> None:
        self.upper = upper
        self.lower = lower
        self.edge_index = edge_index
        self.x_out = 0.0
        self.y_out = 0.0
        self.x_in = 0.0
        self.y_in = 0.0
        self.channel_y: float | None = None


class FigureLayoutError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def size_nodes(nodes: list[Node], fig_type: str) -> None:
    max_units = MAX_UNITS.get(fig_type, 16)
    for node in nodes:
        if node.dummy:
            node.w, node.h = 0.0, 0.0
            continue
        units = max_units * (0.62 if node.shape == "decision" else 1.0)
        node.lines = wrap_text(node.label, units)
    text_w = max((max(text_units(l) for l in n.lines) * FONT for n in nodes if not n.dummy), default=0)
    uniform_w = max(MIN_NODE_W, text_w + 2 * PAD_X)
    for node in nodes:
        if node.dummy:
            continue
        text_h = len(node.lines) * LINE_H
        if node.shape == "decision":
            own_w = max(text_units(l) for l in node.lines) * FONT
            node.w = max(own_w * 1.9 + 24, 220)
            node.h = max(text_h * 2.0 + 20, 110)
        else:
            node.w = uniform_w
            node.h = max(text_h + 2 * PAD_Y, 64)


def find_back_edges(order: list[str], edges: list[tuple[str, str]]) -> set[int]:
    adjacency: dict[str, list[tuple[int, str]]] = {nid: [] for nid in order}
    for idx, (src, dst) in enumerate(edges):
        adjacency[src].append((idx, dst))
    state: dict[str, int] = {}
    back: set[int] = set()
    sys.setrecursionlimit(max(1000, len(order) * 4 + 100))

    def dfs(u: str) -> None:
        state[u] = 1
        for idx, v in adjacency[u]:
            if state.get(v) == 1:
                back.add(idx)
            elif not state.get(v):
                dfs(v)
        state[u] = 2

    for nid in order:
        if not state.get(nid):
            dfs(nid)
    return back


def longest_path_layers(order: list[str], dag: list[tuple[str, str]]) -> dict[str, int]:
    indeg = {nid: 0 for nid in order}
    succ: dict[str, list[str]] = {nid: [] for nid in order}
    for s, t in dag:
        indeg[t] += 1
        succ[s].append(t)
    layer = {nid: 0 for nid in order}
    sources = [nid for nid in order if indeg[nid] == 0]
    ready = list(sources)
    position = {nid: i for i, nid in enumerate(order)}
    while ready:
        ready.sort(key=lambda n: position[n])
        u = ready.pop(0)
        for v in succ[u]:
            layer[v] = max(layer[v], layer[u] + 1)
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
    # Pull secondary inputs down next to their consumer to avoid long edges.
    for nid in sources:
        if succ[nid]:
            layer[nid] = max(layer[nid], min(layer[v] for v in succ[nid]) - 1)
    return layer


def isotonic_place(desired: list[float], seps: list[float], weights: list[float]) -> list[float]:
    """Positions closest to `desired` with x[i+1]-x[i] >= seps[i] (weighted PAV)."""
    n = len(desired)
    if n == 0:
        return []
    offsets = [0.0] * n
    for i in range(1, n):
        offsets[i] = offsets[i - 1] + seps[i - 1]
    values = [desired[i] - offsets[i] for i in range(n)]
    blocks: list[list[float]] = []  # [value, weight, count]
    for v, w in zip(values, weights):
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            v2, w2, c2 = blocks.pop()
            v1, w1, c1 = blocks.pop()
            total = w1 + w2
            blocks.append([(v1 * w1 + v2 * w2) / total, total, c1 + c2])
    fitted: list[float] = []
    for v, _, c in blocks:
        fitted.extend([v] * c)
    return [fitted[i] + offsets[i] for i in range(n)]


def layout_figure(fig: dict[str, Any]) -> dict[str, Any]:
    fig_type = "block" if str(fig.get("type", "")).lower() in {"block", "system_block", "module", "device", "data_flow"} else "flowchart"
    raw_nodes = fig.get("nodes") or []
    if not raw_nodes:
        raise FigureLayoutError(f"图{fig.get('figure_no')}: no nodes. Provide explicit nodes taken from the source.")
    nodes: dict[str, Node] = {}
    order: list[str] = []
    for i, raw in enumerate(raw_nodes):
        nid = raw["id"]
        if nid in nodes:
            raise FigureLayoutError(f"图{fig.get('figure_no')}: duplicate node id {nid}.")
        label = str(raw.get("label") or "").strip()
        if not label:
            raise FigureLayoutError(f"图{fig.get('figure_no')}: node {nid} has an empty label.")
        nodes[nid] = Node(nid, label, raw.get("shape", "process"), raw.get("ref"), order_hint=i)
        order.append(nid)

    edges: list[dict[str, Any]] = []
    warnings: list[str] = []
    for edge in fig.get("edges") or []:
        if edge["from"] not in nodes or edge["to"] not in nodes:
            raise FigureLayoutError(
                f"图{fig.get('figure_no')}: edge {edge['from']}->{edge['to']} references an unknown node."
            )
        if edge["from"] == edge["to"]:
            warnings.append(f"self-loop on {edge['from']} ignored")
            continue
        edges.append(edge)

    pairs = [(e["from"], e["to"]) for e in edges]
    back = find_back_edges(order, pairs)
    dag = [(t, s) if i in back else (s, t) for i, (s, t) in enumerate(pairs)]
    layers_of = longest_path_layers(order, dag)
    for nid, layer in layers_of.items():
        nodes[nid].layer = layer

    # Dummy nodes for forward edges spanning several layers. Back edges (loops)
    # are routed later through a side lane, flowchart style.
    chains: dict[int, list[str]] = {}
    dummy_count = 0
    for idx, (s, t) in enumerate(dag):
        if idx in back:
            continue
        chain = [s]
        for layer in range(nodes[s].layer + 1, nodes[t].layer):
            dummy_count += 1
            did = f"__d{dummy_count}"
            dummy = Node(did, dummy=True, order_hint=nodes[s].order_hint)
            dummy.layer = layer
            nodes[did] = dummy
            chain.append(did)
        chain.append(t)
        chains[idx] = chain

    size_nodes(list(nodes.values()), fig_type)

    max_layer = max(n.layer for n in nodes.values())
    layers: list[list[str]] = [[] for _ in range(max_layer + 1)]
    for nid in order:
        layers[nodes[nid].layer].append(nid)
    for nid, node in nodes.items():
        if node.dummy:
            layers[node.layer].append(nid)

    preds: dict[str, list[str]] = {nid: [] for nid in nodes}
    succs: dict[str, list[str]] = {nid: [] for nid in nodes}
    segments: list[Segment] = []
    for idx, chain in chains.items():
        for upper, lower in zip(chain, chain[1:]):
            succs[upper].append(lower)
            preds[lower].append(upper)
            segments.append(Segment(upper, lower, idx))

    # Crossing reduction: barycentre sweeps.
    def reorder(layer_ids: list[str], neighbours: dict[str, list[str]], ref_pos: dict[str, int]) -> list[str]:
        keyed = []
        for i, nid in enumerate(layer_ids):
            ns = [ref_pos[m] for m in neighbours[nid] if m in ref_pos]
            key = sum(ns) / len(ns) if ns else float(i)
            keyed.append((key, i, nid))
        keyed.sort(key=lambda item: (item[0], item[1]))
        return [nid for _, _, nid in keyed]

    for _ in range(4):
        for li in range(1, len(layers)):
            pos = {nid: i for i, nid in enumerate(layers[li - 1])}
            layers[li] = reorder(layers[li], preds, pos)
        for li in range(len(layers) - 2, -1, -1):
            pos = {nid: i for i, nid in enumerate(layers[li + 1])}
            layers[li] = reorder(layers[li], succs, pos)

    # Horizontal placement.
    def separation(a: Node, b: Node) -> float:
        gap = DUMMY_GAP if (a.dummy or b.dummy) else H_GAP
        return a.half_right() + gap + b.half_left()

    for layer_ids in layers:
        seps = [separation(nodes[a], nodes[b]) for a, b in zip(layer_ids, layer_ids[1:])]
        x = -sum(seps) / 2
        for i, nid in enumerate(layer_ids):
            nodes[nid].x = x
            if i < len(seps):
                x += seps[i]

    def place(layer_ids: list[str], neighbours: dict[str, list[str]]) -> None:
        desired, weights = [], []
        for nid in layer_ids:
            node = nodes[nid]
            ns = neighbours[nid]
            real = [m for m in ns if not nodes[m].dummy]
            ns = real or ns  # align with real neighbours; bends of long edges only as fallback
            desired.append(sum(nodes[m].x for m in ns) / len(ns) if ns else node.x)
            # Dummies (bends of long edges) yield to real nodes so main flows stay straight.
            weights.append(1e-4 if node.dummy else (1.0 if ns else 0.5))
        seps = [separation(nodes[a], nodes[b]) for a, b in zip(layer_ids, layer_ids[1:])]
        for nid, x in zip(layer_ids, isotonic_place(desired, seps, weights)):
            nodes[nid].x = x

    for _ in range(3):
        for li in range(1, len(layers)):
            place(layers[li], preds)
        for li in range(len(layers) - 2, -1, -1):
            place(layers[li], succs)
    for li in range(1, len(layers)):
        place(layers[li], preds)

    # Ports: an aligned real neighbour gets the centre; others fan out by side.
    out_ports: dict[str, list[Segment]] = {nid: [] for nid in nodes}
    in_ports: dict[str, list[Segment]] = {nid: [] for nid in nodes}
    for seg in segments:
        out_ports[seg.upper].append(seg)
        in_ports[seg.lower].append(seg)

    def assign_ports(node: Node, segs: list[Segment], other_of, setter) -> None:
        if node.dummy or len(segs) <= 1:
            for seg in segs:
                setter(seg, node.x)
            return
        segs.sort(key=lambda sg: nodes[other_of(sg)].x)
        others = [nodes[other_of(sg)] for sg in segs]
        aligned = [i for i, o in enumerate(others) if abs(o.x - node.x) < 1.0 and not o.dummy]
        limit = node.w * (0.17 if node.shape == "decision" else 0.32)
        if aligned:
            centre = aligned[0]
            left = list(range(centre - 1, -1, -1))
            right = list(range(centre + 1, len(segs)))
            step = min(48.0, limit / max(len(left), len(right), 1))
            setter(segs[centre], node.x)
            for k, i in enumerate(left):
                setter(segs[i], node.x - step * (k + 1))
            for k, i in enumerate(right):
                setter(segs[i], node.x + step * (k + 1))
        else:
            span = min(2 * limit, 56.0 * (len(segs) - 1))
            for i, seg in enumerate(segs):
                setter(seg, node.x - span / 2 + span * i / (len(segs) - 1))

    for nid, segs in out_ports.items():
        assign_ports(nodes[nid], segs, lambda sg: sg.lower, lambda sg, v: setattr(sg, "x_out", v))
    for nid, segs in in_ports.items():
        assign_ports(nodes[nid], segs, lambda sg: sg.upper, lambda sg, v: setattr(sg, "x_in", v))

    # Snap near-vertical one-to-one links to a straight line (no small jogs):
    # a single port may sit anywhere along the facing edge of its box.
    def span_ok(node: Node, x: float) -> bool:
        if node.dummy:
            return abs(x - node.x) < 0.5
        half = node.w * (0.25 if node.shape == "decision" else 0.42)
        return abs(x - node.x) <= half

    for seg in segments:
        if abs(seg.x_out - seg.x_in) <= 0.5:
            continue
        upper, lower = nodes[seg.upper], nodes[seg.lower]
        if len(in_ports[seg.lower]) == 1 and span_ok(lower, seg.x_out):
            seg.x_in = seg.x_out
        elif len(out_ports[seg.upper]) == 1 and span_ok(upper, seg.x_in):
            seg.x_out = seg.x_in

    # Vertical placement with channels per gap.
    layer_heights = [max((nodes[n].h for n in ids if not nodes[n].dummy), default=0.0) for ids in layers]
    gap_segments: list[list[Segment]] = [[] for _ in range(len(layers))]
    for seg in segments:
        if abs(seg.x_out - seg.x_in) > 0.5:
            gap_segments[nodes[seg.upper].layer].append(seg)
    y = 0.0
    layer_tops: list[float] = []
    for li, ids in enumerate(layers):
        layer_tops.append(y)
        for nid in ids:
            node = nodes[nid]
            node.y = y + (layer_heights[li] - node.h) / 2 if not node.dummy else y
            if node.dummy:
                node.h = layer_heights[li]
        channels = len(gap_segments[li])
        gap = V_GAP_BASE + CHANNEL_STEP * max(0, channels - 1)
        if any("label" in edges[sg.edge_index] for sg in out_ports_all(ids, out_ports)):
            gap += 10
        y += layer_heights[li] + gap
    for li, segs in enumerate(gap_segments):
        if not segs or li + 1 >= len(layers):
            continue
        gap_top = layer_tops[li] + layer_heights[li]
        gap_bottom = layer_tops[li + 1]
        # Crossing-free order for orthogonal routing: right-going links whose
        # source is further right take higher channels; left-going links whose
        # source is further left take higher channels.
        rightward = sorted((sg for sg in segs if sg.x_in > sg.x_out), key=lambda sg: (-sg.x_out, -sg.x_in))
        leftward = sorted((sg for sg in segs if sg.x_in < sg.x_out), key=lambda sg: (sg.x_out, sg.x_in))
        segs = rightward + leftward
        for i, seg in enumerate(segs):
            seg.channel_y = gap_top + (gap_bottom - gap_top) * (i + 1) / (len(segs) + 1)

    for seg in segments:
        seg.y_out = boundary_y(nodes[seg.upper], seg.x_out, bottom=True)
        seg.y_in = boundary_y(nodes[seg.lower], seg.x_in, bottom=False)

    # Assemble edge polylines in original direction.
    edge_paths: list[dict[str, Any] | None] = [None] * len(edges)
    for idx, chain in chains.items():
        points: list[tuple[float, float]] = []
        chain_segments = sorted((sg for sg in segments if sg.edge_index == idx), key=lambda sg: nodes[sg.upper].layer)
        for seg in chain_segments:
            points.append((seg.x_out, seg.y_out))
            if seg.channel_y is not None:
                points += [(seg.x_out, seg.channel_y), (seg.x_in, seg.channel_y)]
            points.append((seg.x_in, seg.y_in))  # dummy hops are collinear and merged by simplify()
        edge = edges[idx]
        edge_paths[idx] = {"points": simplify(points), "label": edge.get("label"), "both": bool(edge.get("both"))}

    # Back edges: leave the lower node sideways, run up a lane outside every
    # node in the spanned layers, enter the upper node from the same side.
    back_sorted = sorted(back, key=lambda i: nodes[edges[i]["from"]].layer - nodes[edges[i]["to"]].layer)
    lane_count = {"right": 0, "left": 0}
    # Several loops leaving (or entering) the same box get separate stubs: the
    # loop with the shortest span (innermost lane) uses the uppermost stub, so
    # stubs and lanes never cross.
    from_total: dict[str, int] = {}
    to_total: dict[str, int] = {}
    for idx in back_sorted:
        from_total[edges[idx]["from"]] = from_total.get(edges[idx]["from"], 0) + 1
        to_total[edges[idx]["to"]] = to_total.get(edges[idx]["to"], 0) + 1
    from_seen: dict[str, int] = {}
    to_seen: dict[str, int] = {}

    def stub_y(node: Node, index: int, total: int, default: float) -> float:
        if total <= 1:
            return default
        span = min(node.h * (0.5 if node.shape == "decision" else 0.6), 16.0 * (total - 1))
        return node.cy - span / 2 + span * index / (total - 1)

    def side_x(node: Node, y: float, side: str) -> float:
        half = node.w / 2
        if node.shape == "decision":  # diamond boundary at height y
            half = node.w / 2 * max(0.0, 1 - abs(y - node.cy) / (node.h / 2))
        return node.x + half if side == "right" else node.x - half

    for idx in back_sorted:
        src, dst = nodes[edges[idx]["from"]], nodes[edges[idx]["to"]]
        lo, hi = dst.layer, src.layer
        spanned = [nodes[n] for li in range(lo, hi + 1) for n in layers[li]]

        def blockers(node: Node, side: str) -> int:
            """Real boxes the horizontal stub would cut through on this side."""
            row = [nodes[n] for n in layers[node.layer] if not nodes[n].dummy and n != node.id]
            if side == "right":
                return sum(1 for o in row if o.x > node.x)
            return sum(1 for o in row if o.x < node.x)

        cost = {s: blockers(src, s) + blockers(dst, s) for s in ("right", "left")}
        side = "right" if cost["right"] <= cost["left"] else "left"
        if cost[side]:
            warnings.append(
                f"loop {edges[idx]['from']}->{edges[idx]['to']} crosses {cost[side]} box(es); "
                "reorder `nodes` so loop endpoints are outermost in their rows"
            )
        k = lane_count[side]
        lane_count[side] += 1
        if side == "right":
            lane_x = max(n.x + n.half_right() for n in spanned) + 30 + 22 * k
        else:
            lane_x = min(n.x - n.half_left() for n in spanned) - 30 - 22 * k
        fi = from_seen.get(src.id, 0)
        from_seen[src.id] = fi + 1
        ti = to_seen.get(dst.id, 0)
        to_seen[dst.id] = ti + 1
        default_sy = src.cy if src.shape == "decision" else src.cy + min(10.0, src.h / 4)
        default_dy = dst.cy if dst.shape == "decision" else dst.cy - min(10.0, dst.h / 4)
        sy = stub_y(src, fi, from_total[src.id], default_sy)
        dy = stub_y(dst, ti, to_total[dst.id], default_dy)
        sx, dx = side_x(src, sy, side), side_x(dst, dy, side)
        edge = edges[idx]
        edge_paths[idx] = {
            "points": [(sx, sy), (lane_x, sy), (lane_x, dy), (dx, dy)],
            "label": edge.get("label"),
            "both": bool(edge.get("both")),
            "back": True,
        }

    real_nodes = [n for n in nodes.values() if not n.dummy]
    container = fig.get("container") if isinstance(fig.get("container"), dict) else None
    return {
        "type": fig_type,
        "nodes": real_nodes,
        "edges": [p for p in edge_paths if p],
        "container": container,
        "back_edges": len(back),
        "warnings": warnings,
    }


def out_ports_all(ids: list[str], out_ports: dict[str, list[Segment]]) -> list[Segment]:
    result: list[Segment] = []
    for nid in ids:
        result.extend(out_ports[nid])
    return result


def boundary_y(node: Node, x: float, bottom: bool) -> float:
    if node.dummy:
        return node.y + (node.h if bottom else 0.0)
    if node.shape == "decision":
        half_w = node.w / 2
        frac = min(1.0, abs(x - node.x) / half_w) if half_w else 0.0
        dy = node.h / 2 * (1 - frac)
        return node.cy + dy if bottom else node.cy - dy
    return node.y + node.h if bottom else node.y


def simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    cleaned: list[tuple[float, float]] = []
    for p in points:
        if cleaned and abs(cleaned[-1][0] - p[0]) < 0.5 and abs(cleaned[-1][1] - p[1]) < 0.5:
            continue
        cleaned.append(p)
    result: list[tuple[float, float]] = []
    for p in cleaned:
        if len(result) >= 2:
            a, b = result[-2], result[-1]
            collinear_x = abs(a[0] - b[0]) < 0.5 and abs(b[0] - p[0]) < 0.5
            collinear_y = abs(a[1] - b[1]) < 0.5 and abs(b[1] - p[1]) < 0.5
            if collinear_x or collinear_y:
                result[-1] = p
                continue
        result.append(p)
    return result


# ---------------------------------------------------------------------------
# Geometry -> primitives (shared by SVG and PNG renderers)
# ---------------------------------------------------------------------------

def build_primitives(layout: dict[str, Any]) -> tuple[list[dict[str, Any]], tuple[float, float, float, float]]:
    prims: list[dict[str, Any]] = []
    xs: list[float] = []
    ys: list[float] = []

    def track(x: float, y: float) -> None:
        xs.append(x)
        ys.append(y)

    pending_labels: list[tuple[str, list[tuple[float, float]], bool]] = []
    node_rects = [(n.x - n.w / 2, n.y, n.x + n.w / 2, n.y + n.h) for n in layout["nodes"]]

    for edge in layout["edges"]:
        pts = edge["points"]
        if len(pts) < 2:
            continue
        prims.append({"kind": "polyline", "points": pts})
        prims.append({"kind": "arrow", "tip": pts[-1], "from": pts[-2]})
        if edge["both"]:
            prims.append({"kind": "arrow", "tip": pts[0], "from": pts[1]})
        for p in pts:
            track(*p)
        if edge.get("label"):
            pending_labels.append((edge["label"], pts, bool(edge.get("back"))))

    for node in layout["nodes"]:
        left, top = node.x - node.w / 2, node.y
        prims.append({"kind": "shape", "shape": node.shape, "x": left, "y": top, "w": node.w, "h": node.h})
        prims.append({"kind": "text", "x": node.x, "y": node.cy, "lines": node.lines, "anchor": "middle", "size": FONT})
        track(left, top)
        track(left + node.w, top + node.h)
        if node.ref:
            rx = left + node.w
            ry = top + min(node.h * 0.3, 22)
            end = (rx + 18, ry - 14)
            prims.append({"kind": "line", "points": [(rx - 4, ry + 4), end]})
            prims.append({"kind": "text", "x": end[0] + 3, "y": end[1] - 2, "lines": [node.ref], "anchor": "start", "size": FONT})
            track(end[0] + 3 + text_units(node.ref) * FONT, end[1] - 2 - FONT * 0.6)

    for label, pts, is_back in pending_labels:
        lx, ly = place_label(label, pts, node_rects, prefer_last=is_back and text_units(label) > 2)
        size = FONT - 4
        lw = text_units(label) * size
        prims.append({"kind": "bgrect", "x": lx - 2, "y": ly - size * 0.6, "w": lw + 4, "h": size * 1.2})
        prims.append({"kind": "text", "x": lx, "y": ly, "lines": [label], "anchor": "start", "size": size})
        track(lx + lw, ly - size * 0.6)
        track(lx, ly + size * 0.6)

    container = layout.get("container")
    if container and xs:
        pad = 26
        label = str(container.get("label") or "").strip()
        top_extra = LINE_H + 6 if label else 0
        left, top = min(xs) - pad, min(ys) - pad - top_extra
        right, bottom = max(xs) + pad, max(ys) + pad
        prims.insert(0, {"kind": "shape", "shape": "process", "x": left, "y": top, "w": right - left, "h": bottom - top})
        if label:
            prims.append({"kind": "text", "x": left + 14, "y": top + 6 + LINE_H / 2, "lines": [label], "anchor": "start", "size": FONT})
        if container.get("ref"):
            ref = str(container["ref"])
            end = (right + 18, top - 14)
            prims.append({"kind": "line", "points": [(right - 4, top + 6), end]})
            prims.append({"kind": "text", "x": end[0] + 3, "y": end[1] - 2, "lines": [ref], "anchor": "start", "size": FONT})
            track(end[0] + 3 + text_units(ref) * FONT, end[1] - 2 - FONT * 0.6)
        track(left, top)
        track(right, bottom)

    bbox = (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 1.0, 1.0)
    return prims, bbox


def place_label(label: str, pts: list[tuple[float, float]],
                node_rects: list[tuple[float, float, float, float]],
                prefer_last: bool = False) -> tuple[float, float]:
    """Pick a label position beside an edge that does not cover any node."""
    size = FONT - 4
    lw, lh = text_units(label) * size, size * 1.2

    def clear(x: float, y: float) -> bool:
        box = (x - 3, y - lh / 2 - 3, x + lw + 3, y + lh / 2 + 3)
        return not any(box[0] < r[2] and box[2] > r[0] and box[1] < r[3] and box[3] > r[1] for r in node_rects)

    legs = list(zip(pts, pts[1:]))
    if prefer_last:
        # Loop labels sit on the leg entering the target, where each loop is distinct.
        legs = [legs[-1]] + legs[:-1]
    elif text_units(label) > 2:
        legs.sort(key=lambda ab: -math.hypot(ab[1][0] - ab[0][0], ab[1][1] - ab[0][1]))
    candidates: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in legs:
        if abs(x0 - x1) < 0.5:
            for t in ((0.25, 0.5, 0.75) if text_units(label) > 2 else (0.0, 0.3, 0.6)):
                yy = y0 + (y1 - y0) * t + (lh / 2 + 4 if t == 0.0 and y1 > y0 else 0) - (lh / 2 + 4 if t == 0.0 and y1 < y0 else 0)
                candidates += [(x0 + 7, yy), (x0 - 7 - lw, yy)]
        else:
            xm = min(x0, x1) + abs(x1 - x0) * 0.5 - lw / 2
            candidates += [(xm, y0 - lh / 2 - 4), (xm, y0 + lh / 2 + 4)]
    for x, y in candidates:
        if clear(x, y):
            return x, y
    return candidates[0] if candidates else (pts[0][0] + 7, pts[0][1])


def arrow_polygon(tip: tuple[float, float], frm: tuple[float, float]) -> list[tuple[float, float]]:
    angle = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
    base_x = tip[0] - ARROW_LEN * math.cos(angle)
    base_y = tip[1] - ARROW_LEN * math.sin(angle)
    perp = angle + math.pi / 2
    return [
        tip,
        (base_x + ARROW_HALF * math.cos(perp), base_y + ARROW_HALF * math.sin(perp)),
        (base_x - ARROW_HALF * math.cos(perp), base_y - ARROW_HALF * math.sin(perp)),
    ]


def shorten_for_arrow(points: list[tuple[float, float]], at_end: bool, at_start: bool) -> list[tuple[float, float]]:
    pts = list(points)

    def pull(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
        dx, dy = a[0] - b[0], a[1] - b[1]
        dist = math.hypot(dx, dy) or 1.0
        cut = min(ARROW_LEN - 2, dist)
        return (a[0] - dx / dist * cut, a[1] - dy / dist * cut)

    if at_end and len(pts) >= 2:
        pts[-1] = pull(pts[-1], pts[-2])
    if at_start and len(pts) >= 2:
        pts[0] = pull(pts[0], pts[1])
    return pts


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

SVG_FONT_FAMILY = "SimSun, 'Songti SC', 'Noto Serif CJK SC', 'Source Han Serif SC', 'Noto Sans CJK SC', serif"


def fmt(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def render_svg(prims: list[dict[str, Any]], bbox: tuple[float, float, float, float]) -> tuple[str, int, int]:
    ox, oy = MARGIN - bbox[0], MARGIN - bbox[1]
    width = math.ceil(bbox[2] - bbox[0] + 2 * MARGIN)
    height = math.ceil(bbox[3] - bbox[1] + 2 * MARGIN)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
    ]
    arrows = [p for p in prims if p["kind"] == "arrow"]
    tips = {tuple(a["tip"]) for a in arrows}
    for prim in prims:
        kind = prim["kind"]
        if kind == "shape":
            x, y, w, h = prim["x"] + ox, prim["y"] + oy, prim["w"], prim["h"]
            if prim["shape"] == "decision":
                pts = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
                out.append(f'<polygon points="{" ".join(f"{fmt(a)},{fmt(b)}" for a, b in pts)}" fill="#ffffff" stroke="#000000" stroke-width="{STROKE}"/>')
            else:
                rx = h / 2 if prim["shape"] == "terminal" else 0
                out.append(f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{fmt(rx)}" ry="{fmt(rx)}" fill="#ffffff" stroke="#000000" stroke-width="{STROKE}"/>')
        elif kind == "bgrect":
            out.append(f'<rect x="{fmt(prim["x"] + ox)}" y="{fmt(prim["y"] + oy)}" width="{fmt(prim["w"])}" height="{fmt(prim["h"])}" fill="#ffffff" stroke="none"/>')
        elif kind == "polyline":
            pts = shorten_for_arrow(prim["points"], tuple(prim["points"][-1]) in tips, tuple(prim["points"][0]) in tips)
            out.append(f'<polyline points="{" ".join(f"{fmt(a + ox)},{fmt(b + oy)}" for a, b in pts)}" fill="none" stroke="#000000" stroke-width="{STROKE}"/>')
        elif kind == "line":
            pts = prim["points"]
            out.append(f'<polyline points="{" ".join(f"{fmt(a + ox)},{fmt(b + oy)}" for a, b in pts)}" fill="none" stroke="#000000" stroke-width="{STROKE - 0.5}"/>')
        elif kind == "arrow":
            poly = arrow_polygon(prim["tip"], prim["from"])
            out.append(f'<polygon points="{" ".join(f"{fmt(a + ox)},{fmt(b + oy)}" for a, b in poly)}" fill="#000000" stroke="none"/>')
        elif kind == "text":
            size = prim["size"]
            lines = prim["lines"]
            line_h = LINE_H * size / FONT
            start = prim["y"] - (len(lines) - 1) * line_h / 2
            for i, line in enumerate(lines):
                yy = start + i * line_h + size * 0.36
                out.append(
                    f'<text x="{fmt(prim["x"] + ox)}" y="{fmt(yy + oy)}" text-anchor="{prim["anchor"]}" '
                    f'font-family="{SVG_FONT_FAMILY}" font-size="{size}" fill="#000000">{escape(line)}</text>'
                )
    out.append("</svg>")
    return "\n".join(out) + "\n", width, height


def render_png(prims: list[dict[str, Any]], bbox: tuple[float, float, float, float], output: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for PNG output (pip install pillow).") from exc
    s = PNG_SCALE
    ox, oy = MARGIN - bbox[0], MARGIN - bbox[1]
    width = math.ceil((bbox[2] - bbox[0] + 2 * MARGIN) * s)
    height = math.ceil((bbox[3] - bbox[1] + 2 * MARGIN) * s)
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    fonts: dict[int, Any] = {}

    def font(size: int):
        if size not in fonts:
            fonts[size] = load_cjk_font(int(size * s))
        return fonts[size]

    def tp(p: tuple[float, float]) -> tuple[float, float]:
        return ((p[0] + ox) * s, (p[1] + oy) * s)

    arrows = [p for p in prims if p["kind"] == "arrow"]
    tips = {tuple(a["tip"]) for a in arrows}
    lw = max(1, int(round(STROKE * s)))
    for prim in prims:
        kind = prim["kind"]
        if kind == "shape":
            x0, y0 = tp((prim["x"], prim["y"]))
            x1, y1 = tp((prim["x"] + prim["w"], prim["y"] + prim["h"]))
            if prim["shape"] == "decision":
                pts = [((x0 + x1) / 2, y0), (x1, (y0 + y1) / 2), ((x0 + x1) / 2, y1), (x0, (y0 + y1) / 2)]
                draw.polygon(pts, fill=255)
                draw.line(pts + [pts[0]], fill=0, width=lw, joint="curve")
            elif prim["shape"] == "terminal":
                draw.rounded_rectangle((x0, y0, x1, y1), radius=(y1 - y0) / 2, outline=0, width=lw, fill=255)
            else:
                draw.rectangle((x0, y0, x1, y1), outline=0, width=lw, fill=255)
        elif kind == "bgrect":
            x0, y0 = tp((prim["x"], prim["y"]))
            x1, y1 = tp((prim["x"] + prim["w"], prim["y"] + prim["h"]))
            draw.rectangle((x0, y0, x1, y1), fill=255)
        elif kind in {"polyline", "line"}:
            pts = prim["points"]
            if kind == "polyline":
                pts = shorten_for_arrow(pts, tuple(pts[-1]) in tips, tuple(pts[0]) in tips)
            width_px = lw if kind == "polyline" else max(1, int(round((STROKE - 0.5) * s)))
            draw.line([tp(p) for p in pts], fill=0, width=width_px, joint="curve")
        elif kind == "arrow":
            draw.polygon([tp(p) for p in arrow_polygon(prim["tip"], prim["from"])], fill=0)
        elif kind == "text":
            size = prim["size"]
            f = font(size)
            lines = prim["lines"]
            line_h = LINE_H * size / FONT
            start = prim["y"] - (len(lines) - 1) * line_h / 2
            for i, line in enumerate(lines):
                cx, cy = tp((prim["x"], start + i * line_h))
                anchor = "mm" if prim["anchor"] == "middle" else "lm"
                draw.text((cx, cy), line, fill=0, font=f, anchor=anchor)
    image.save(output, dpi=(300, 300))


# ---------------------------------------------------------------------------
# Validation, prompts, driver
# ---------------------------------------------------------------------------

def validate(fig: dict[str, Any], layout: dict[str, Any], bbox: tuple[float, float, float, float],
             width: int, height: int) -> dict[str, Any]:
    issues: list[str] = []
    for node in layout["nodes"]:
        if FIGURE_NO_RE.search(node.label):
            issues.append(f"node {node.id} label contains a figure number")
    title = str(fig.get("title") or "")
    if title and any(title == n.label for n in layout["nodes"]):
        issues.append("figure title drawn as a node")
    connected = set()
    for edge in fig.get("edges") or []:
        connected.add(edge["from"])
        connected.add(edge["to"])
    isolated = [n.id for n in layout["nodes"] if n.id not in connected]
    warnings = list(layout.get("warnings", []))
    if len(layout["nodes"]) > 1 and isolated:
        warnings.append(f"isolated nodes (no edges): {', '.join(isolated)}")
    content_w = bbox[2] - bbox[0]
    content_h = bbox[3] - bbox[1]
    w_ratio = round(content_w / width, 3) if width else 0
    h_ratio = round(content_h / height, 3) if height else 0
    # Printed text size when the DOCX fits the figure into 15 cm x 20 cm.
    scale_cm_per_px = min(PRINT_MAX_W_CM / width, PRINT_MAX_H_CM / height) if width and height else 0
    text_mm = round(FONT * 0.8 * scale_cm_per_px * 10, 2)  # CJK glyphs fill ~80% of the em box
    if text_mm and text_mm < MIN_TEXT_MM:
        warnings.append(
            f"printed text height ≈ {text_mm} mm (< {MIN_TEXT_MM} mm): split the figure, shorten labels "
            "or reduce the number of nodes per row"
        )
    if len(layout["nodes"]) > MAX_NODES_HINT:
        warnings.append(f"{len(layout['nodes'])} nodes; figures over ~{MAX_NODES_HINT} nodes are hard to read — consider splitting")
    return {
        "canvas_width": width,
        "canvas_height": height,
        "content_width_ratio": w_ratio,
        "content_height_ratio": h_ratio,
        "nodes": len(layout["nodes"]),
        "edges": len(layout["edges"]),
        "back_edges": layout.get("back_edges", 0),
        "printed_text_mm": text_mm,
        "internal_title": False,
        "issues": issues,
        "warnings": warnings,
        "passes": not issues and w_ratio >= 0.8 and h_ratio >= 0.8 and text_mm >= MIN_TEXT_MM,
    }


def image_model_prompt(fig: dict[str, Any]) -> str:
    labels = {n["id"]: n["label"] for n in fig.get("nodes") or []}
    node_text = "；".join(
        f"{n['label']}" + (f"（标号{n['ref']}）" if n.get("ref") else "") + ("（菱形判断框）" if n.get("shape") == "decision" else "")
        for n in fig.get("nodes") or []
    )
    edge_text = "；".join(
        f"{labels.get(e['from'], e['from'])}{'↔' if e.get('both') else '→'}{labels.get(e['to'], e['to'])}"
        + ("（双向箭头）" if e.get("both") else "")
        + (f"（{e['label']}）" if e.get("label") else "")
        for e in fig.get("edges") or []
    )
    return (
        f"请以附带的参考图为结构底稿，重绘中国发明专利申请说明书附图图{fig['figure_no']}。"
        f"节点（仅限以下内容，文字逐字保留）：{node_text}。连接关系（仅限以下箭头）：{edge_text or '无'}。"
        "硬性要求：纯黑白线条图、白色背景，不得有彩色、灰度、渐变、阴影、三维效果、图标、logo或水印；"
        "图内不得出现图号、附图标题或说明性段落；不得新增、删除、合并任何节点或箭头，不得改变方向；"
        "版面紧凑，主体内容占画布宽高80%以上；文字清晰，缩小到三分之二仍可辨认。"
    )


def generate(data: dict[str, Any], json_path: Path, output_dir: Path, prefix: str, png: bool = True) -> tuple[list[dict[str, Any]], list[str]]:
    figures, warnings = normalize_drawings(data)
    if not figures:
        raise ValueError("The JSON has no `drawings` entries.")
    output_dir.mkdir(parents=True, exist_ok=True)
    assets: list[dict[str, Any]] = []
    errors: list[str] = []
    for fig in figures:
        n = fig["figure_no"]
        try:
            layout = layout_figure(fig)
        except FigureLayoutError as exc:
            errors.append(str(exc))
            continue
        prims, bbox = build_primitives(layout)
        svg_text, width, height = render_svg(prims, bbox)
        svg_path = output_dir / f"{prefix}_图{n}.svg"
        svg_path.write_text(svg_text, encoding="utf-8")
        asset: dict[str, Any] = {
            "figure_no": n,
            "title": str(fig.get("title") or "").strip(),
            "type": layout["type"],
            "svg_path": relpath(svg_path, json_path.parent),
            "source": fig.get("source", ""),
        }
        if png:
            png_path = svg_path.with_suffix(".png")
            try:
                render_png(prims, bbox, png_path)
                asset["png_path"] = relpath(png_path, json_path.parent)
            except RuntimeError as exc:
                errors.append(f"图{n}: PNG not written: {exc}")
        asset["validation"] = validate(fig, layout, bbox, width, height)
        asset["image_model_prompt"] = image_model_prompt(fig)
        for w in asset["validation"]["warnings"]:
            warnings.append(f"图{n}: {w}")
        for issue in asset["validation"]["issues"]:
            errors.append(f"图{n}: {issue}")
        assets.append(asset)
    data["drawing_assets"] = assets
    data["image_model_prompts"] = [{"figure_no": a["figure_no"], "prompt": a["image_model_prompt"]} for a in assets]
    return assets, warnings + [f"ERROR: {e}" for e in errors]


def relpath(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate patent drawings (SVG + PNG) from patent content JSON.")
    parser.add_argument("input", type=Path, help="Patent content JSON.")
    parser.add_argument("-o", "--output-dir", type=Path, help="Directory for drawing files (default: JSON folder).")
    parser.add_argument("--prefix", help="File name prefix (default: JSON file stem).")
    parser.add_argument("--no-png", action="store_true", help="Only write SVG files.")
    parser.add_argument("--update-json", action="store_true", help="Write drawing_assets back into the JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = read_json(args.input)
    output_dir = args.output_dir or args.input.parent
    prefix = args.prefix or re.sub(r"_(patent_content|专利申请书)$", "", args.input.stem)
    try:
        assets, messages = generate(data, args.input, output_dir, prefix, png=not args.no_png)
    except ValueError as exc:
        eprint(f"ERROR: {exc}")
        return 2
    if args.update_json:
        write_json(args.input, data)
    for asset in assets:
        v = asset["validation"]
        status = "ok" if v["passes"] else "CHECK"
        print(f"图{asset['figure_no']}: {asset['svg_path']} | {asset.get('png_path', 'no png')} | "
              f"{v['nodes']} nodes, {v['edges']} edges, fill {v['content_width_ratio']}x{v['content_height_ratio']} [{status}]")
    for message in messages:
        eprint(message if message.startswith("ERROR") else f"WARNING: {message}")
    return 1 if any(m.startswith("ERROR") for m in messages) else 0


if __name__ == "__main__":
    raise SystemExit(main())
