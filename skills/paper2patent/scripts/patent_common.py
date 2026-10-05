#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared helpers for the paper2patent scripts.

Standard library only. Pillow is optional and only needed by callers that
render PNG images.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

FIGURE_NO_RE = re.compile(r"图\s*(\d+)")
STEP_ID_RE = re.compile(r"S\d{2,4}")

DESCRIPTION_SECTIONS = [
    ("technical_field", "技术领域"),
    ("background", "背景技术"),
    ("invention_content", "发明内容"),
    ("drawing_description", "附图说明"),
    ("embodiments", "具体实施方式"),
]


# ---------------------------------------------------------------------------
# JSON / text helpers
# ---------------------------------------------------------------------------

def read_json(path: Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("Patent content JSON must be an object.")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def as_paragraphs(value: Any) -> list[str]:
    """Flatten strings / lists / dicts into a list of non-empty paragraphs."""
    if value is None:
        return []
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(as_paragraphs(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(as_paragraphs(item))
        return result
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?:\r?\n)+", text) if part.strip()]


def claims_list(data: dict[str, Any]) -> list[str]:
    raw = data.get("claims")
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return as_paragraphs(raw)


def description_text(data: dict[str, Any]) -> str:
    desc = data.get("description")
    return "\n".join(as_paragraphs(desc))


def abstract_figure_no(data: dict[str, Any]) -> int | None:
    """Return the designated abstract figure number (new or legacy field)."""
    value = data.get("abstract_figure")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    legacy = str(data.get("abstract_drawing") or "")
    match = FIGURE_NO_RE.search(legacy)
    if match:
        return int(match.group(1))
    return None


def visible_len(text: str) -> int:
    """Character count used for CNIPA limits (punctuation counts, whitespace does not)."""
    return len(re.sub(r"\s+", "", text))


def resolve_path(raw: str, base_dir: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    candidate = (base_dir / path)
    if candidate.exists():
        return candidate.resolve()
    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate.resolve()
    return candidate.resolve()


# ---------------------------------------------------------------------------
# Drawings: normalisation of the `drawings` field
# ---------------------------------------------------------------------------

LEGACY_STEP_RE = re.compile(r"(S\d{2,4})[，,:：、\s]*(.*?)(?=(?:[；;。]|S\d{2,4}[，,:：、\s]|$))")


def normalize_drawings(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Return structured figure specs plus warnings.

    Structured form (preferred)::

        {"figure_no": 1, "title": "……的流程示意图", "type": "flowchart",
         "nodes": [{"id": "S101", "label": "S101 获取……"}],
         "edges": [{"from": "S101", "to": "S102"}],
         "source": "论文图2、第3.1节"}

    Legacy form: a plain string such as
    "图1：……流程图，包含步骤S101，……；S102，……". Legacy strings are only
    converted automatically when they contain explicit step numbers; the
    steps are chained in numeric order because a step list is sequential by
    definition. Legacy module lists are converted to nodes *without* edges and
    a warning is returned, because connections must never be guessed.
    """
    raw = data.get("drawings")
    warnings: list[str] = []
    if raw is None:
        return [], warnings
    items = raw if isinstance(raw, list) else as_paragraphs(raw)
    figures: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, dict):
            fig = dict(item)
            fig.setdefault("figure_no", index)
            fig["figure_no"] = int(fig["figure_no"])
            fig.setdefault("type", "flowchart")
            fig["nodes"] = [normalize_node(n, i) for i, n in enumerate(fig.get("nodes") or [], start=1)]
            fig["edges"] = [normalize_edge(e) for e in (fig.get("edges") or [])]
            fig["edges"] = [e for e in fig["edges"] if e]
            figures.append(fig)
            continue
        spec = str(item).strip()
        if not spec:
            continue
        match = FIGURE_NO_RE.search(spec)
        figure_no = int(match.group(1)) if match else index
        title = re.sub(r"^图\s*\d+\s*[：:]\s*", "", spec)
        title = re.split(r"[，,。；;]", title, maxsplit=1)[0].strip()
        steps = [(sid, label.strip()) for sid, label in LEGACY_STEP_RE.findall(spec) if label.strip()]
        fig = {"figure_no": figure_no, "title": title, "legacy_spec": spec}
        if len(steps) >= 2:
            fig["type"] = "flowchart"
            fig["nodes"] = [{"id": sid, "label": f"{sid} {strip_trailing_punct(label)}", "shape": "process"} for sid, label in steps]
            fig["edges"] = [{"from": a[0], "to": b[0]} for a, b in zip(steps, steps[1:])]
            warnings.append(
                f"图{figure_no}: converted from a legacy text spec (steps chained in order). "
                "Prefer the structured nodes/edges form."
            )
        else:
            body = re.sub(r"^.*?包含", "", spec, count=1)
            parts = [strip_trailing_punct(p) for p in re.split(r"[、，,；;]", body)]
            parts = [p for p in parts if 1 < len(p) <= 20 and "图" not in p]
            fig["type"] = "block"
            fig["nodes"] = [{"id": f"N{i}", "label": p, "shape": "process"} for i, p in enumerate(parts, start=1)]
            fig["edges"] = []
            warnings.append(
                f"图{figure_no}: legacy text spec has no explicit connections; nodes were drawn without "
                "edges. Rewrite this figure with explicit nodes/edges taken from the source paper."
            )
        figures.append(fig)
    figures.sort(key=lambda f: f["figure_no"])
    return figures, warnings


def strip_trailing_punct(text: str) -> str:
    return re.sub(r"[。；;，,：:\s]+$", "", text.strip())


def normalize_node(node: Any, index: int) -> dict[str, Any]:
    if isinstance(node, str):
        return {"id": f"N{index}", "label": node, "shape": "process"}
    result = dict(node)
    result["id"] = str(result.get("id") or f"N{index}")
    result["label"] = str(result.get("label") or result["id"]).strip()
    result["shape"] = str(result.get("shape") or "process")
    if result.get("ref") is not None:
        result["ref"] = str(result["ref"])
    return result


def normalize_edge(edge: Any) -> dict[str, Any] | None:
    if isinstance(edge, (list, tuple)) and len(edge) >= 2:
        result = {"from": str(edge[0]), "to": str(edge[1])}
        if len(edge) >= 3 and edge[2]:
            result["label"] = str(edge[2])
        return result
    if isinstance(edge, dict):
        src = edge.get("from") or edge.get("source")
        dst = edge.get("to") or edge.get("target")
        if not src or not dst:
            return None
        result = {"from": str(src), "to": str(dst)}
        if edge.get("label"):
            result["label"] = str(edge["label"])
        if edge.get("both") or edge.get("bidirectional"):
            result["both"] = True
        return result
    return None


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

CJK_FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\simsun.ttc",
    r"C:\Windows\Fonts\simsunb.ttf",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Songti.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
]

_FONT_PATH_CACHE: list[str | None] = []


def find_cjk_font_path() -> str | None:
    """Locate a font file that can render Simplified Chinese.

    Order: $PATENT_CJK_FONT, well-known paths on Windows/macOS/Linux, then
    `fc-match :lang=zh` when fontconfig is installed.
    """
    if _FONT_PATH_CACHE:
        return _FONT_PATH_CACHE[0]
    found: str | None = None
    env = os.environ.get("PATENT_CJK_FONT")
    if env and Path(env).exists():
        found = env
    if not found:
        for candidate in CJK_FONT_CANDIDATES:
            if Path(candidate).exists():
                found = candidate
                break
    if not found and shutil.which("fc-match"):
        try:
            out = subprocess.run(
                ["fc-match", "-f", "%{file}", ":lang=zh-cn"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if out and Path(out).exists():
                found = out
        except (OSError, subprocess.SubprocessError):
            found = None
    _FONT_PATH_CACHE.append(found)
    return found


def load_cjk_font(size: int):
    """Return a Pillow font that renders Chinese, or raise RuntimeError.

    Falling back to Pillow's bitmap font silently produces empty boxes for
    every Chinese character, which is worse than failing, so we refuse.
    """
    try:
        from PIL import ImageFont
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required for PNG rendering (pip install pillow).") from exc
    path = find_cjk_font_path()
    if not path:
        raise RuntimeError(
            "No Chinese-capable font found. Install one (e.g. Noto Serif CJK / SimSun / Songti) "
            "or set PATENT_CJK_FONT=/path/to/font.ttc."
        )
    return ImageFont.truetype(path, size=size)


def text_units(text: str) -> float:
    """Approximate rendered width in em units (CJK = 1, ASCII ≈ 0.6)."""
    units = 0.0
    for ch in text:
        if ord(ch) < 0x2E80:
            units += 0.62 if not ch.isspace() else 0.35
        else:
            units += 1.0
    return units


def wrap_text(text: str, max_units: float) -> list[str]:
    """Wrap a label to lines of at most `max_units`; never truncates.

    Latin words and numbers are kept together where possible.
    """
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return [""]
    tokens = re.findall(r"[A-Za-z0-9_.+\-/%()]+|\s|.", text)
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = current + token
        if current and text_units(candidate) > max_units:
            if token.isspace():
                lines.append(current.rstrip())
                current = ""
                continue
            # Avoid starting a line with closing punctuation.
            if token in "，。；：、）」』,.;:)" and len(current) > 1:
                lines.append(current[:-1])
                current = current[-1] + token
                continue
            lines.append(current.rstrip())
            current = token.lstrip()
        else:
            current = candidate
    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)
