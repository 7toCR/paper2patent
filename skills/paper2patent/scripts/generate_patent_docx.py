#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a Chinese invention patent application DOCX (and drafting notes).

Application file layout (each part starts on a new page, page numbers in the
footer): 说明书摘要 / 摘要附图 / 权利要求书 / 说明书 (with the invention name
and the five standard sub-sections) / 说明书附图 (each figure followed only by
"图N", as in CNIPA filings; figure titles belong in 附图说明).

Everything that is *not* application text - source paper, disclosure and
novelty risks, claim plan, claim-to-source support map, material gaps,
drawing provenance and refinement prompts, automatic check results - goes into
a separate "撰写说明" DOCX so the application file can be handed to an agent
or filed without clean-up.

Standard library only.

Usage:
    python generate_patent_docx.py patent_content.json --output out/申请文件.docx \
        [--notes-output out/撰写说明.docx | --no-notes] [--require-drawings] \
        [--number-paragraphs] [--embed-svg]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import struct
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patent_common import (  # noqa: E402
    DESCRIPTION_SECTIONS,
    abstract_figure_no,
    as_paragraphs,
    claims_list,
    read_json,
    resolve_path,
    text_units,
)

EMU_PER_CM = 360000
MAX_W_CM = 15.0
MAX_H_CM = 20.0
ABSTRACT_MAX_W_CM = 12.0
ABSTRACT_MAX_H_CM = 14.0

NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main"'
)


def x(text: str) -> str:
    return escape(str(text), {'"': "&quot;"})


# ---------------------------------------------------------------------------
# Paragraph builders
# ---------------------------------------------------------------------------

def para(text: str = "", style: str = "Body", align: str | None = None, page_break: bool = False,
         keep_next: bool = False, bold: bool = False) -> str:
    ppr = [f'<w:pStyle w:val="{style}"/>']
    if page_break:
        ppr.append("<w:pageBreakBefore/>")
    if keep_next:
        ppr.append("<w:keepNext/>")
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    rpr = "<w:rPr><w:b/><w:bCs/></w:rPr>" if bold else ""
    run = f'<w:r>{rpr}<w:t xml:space="preserve">{x(text)}</w:t></w:r>' if text else ""
    return f"<w:p><w:pPr>{''.join(ppr)}</w:pPr>{run}</w:p>"


def table(rows: list[list[Any]], caption: str | None = None, align: str = "center") -> str:
    parts = []
    if caption:
        parts.append(para(caption, style="TableCaption", align="center", keep_next=True))
    grid_cols = max(len(r) for r in rows) if rows else 1
    # Column widths follow content length so long names do not break mid-word.
    need = [1.5] * grid_cols
    for row in rows:
        for c, value in enumerate(row):
            longest = max((text_units(part) for part in str(value).split()), default=0.0)
            need[c] = max(need[c], min(text_units(str(value)), 14.0), longest)
    total_need = sum(need)
    floor = min(1000, 9000 // grid_cols)
    widths = [max(floor, int(9000 * n / total_need)) for n in need]
    keep_together = len(rows) <= 15
    xml_rows = []
    for r_index, row in enumerate(rows):
        cells = []
        keep = "<w:keepNext/>" if keep_together and r_index < len(rows) - 1 else ""
        for c, value in enumerate(list(row) + [""] * (grid_cols - len(row))):
            width = widths[c]
            bold = "<w:rPr><w:b/></w:rPr>" if r_index == 0 else ""
            cell_align = "center" if r_index == 0 else align
            cells.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/></w:tcPr>'
                f'<w:p><w:pPr><w:pStyle w:val="TableText"/>{keep}<w:jc w:val="{cell_align}"/></w:pPr>'
                f'<w:r>{bold}<w:t xml:space="preserve">{x(value)}</w:t></w:r></w:p></w:tc>'
            )
        header = "<w:tblHeader/>" if r_index == 0 else ""
        xml_rows.append(f"<w:tr><w:trPr><w:cantSplit/>{header}</w:trPr>{''.join(cells)}</w:tr>")
    borders = "".join(
        f'<w:{side} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
        for side in ("top", "left", "bottom", "right", "insideH", "insideV")
    )
    grid = "".join('<w:gridCol w:w="%d"/>' % w for w in widths)
    parts.append(
        '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/><w:jc w:val="center"/>'
        f"<w:tblBorders>{borders}</w:tblBorders></w:tblPr>"
        f"<w:tblGrid>{grid}</w:tblGrid>"
        + "".join(xml_rows) + "</w:tbl>"
    )
    parts.append(para("", style="Body"))
    return "".join(parts)


class Numberer:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.n = 0

    def __call__(self, text: str) -> str:
        if not self.enabled:
            return text
        self.n += 1
        return f"[{self.n:04d}] {text}"


def section_items(value: Any) -> list[Any]:
    """Items of a description section: strings, or dicts for tables/formulas."""
    if value is None:
        return []
    if isinstance(value, list):
        items: list[Any] = []
        for item in value:
            if isinstance(item, dict):
                items.append(item)
            else:
                items.extend(as_paragraphs(item))
        return items
    if isinstance(value, dict) and ("table" in value or "formula" in value):
        return [value]
    return as_paragraphs(value)


FORMULA_TOKEN_RE = re.compile(r"([_^])(\{[^{}]*\}|\([^()]*\)|[A-Za-z0-9\u0370-\u03ff*'′]+|[^\s{}_^])")


def formula_runs(expr: str) -> str:
    """Render a linear formula with _sub / ^sup (and _{...} / ^{...}) as Word runs.

    Only subscripts and superscripts are typeset; everything else stays as
    typed. Applied to {"formula": ...} items only, never to body text, so
    identifiers such as gt_lyric in ordinary paragraphs are left alone.
    """
    runs = []
    pos = 0
    for match in FORMULA_TOKEN_RE.finditer(expr):
        if match.start() > pos:
            runs.append(("", expr[pos:match.start()]))
        body = match.group(2)
        if body.startswith("{"):
            body = body[1:-1]
        runs.append(("subscript" if match.group(1) == "_" else "superscript", body))
        pos = match.end()
    if pos < len(expr):
        runs.append(("", expr[pos:]))
    xml = []
    for vert, text in runs:
        if not text:
            continue
        rpr = f'<w:rPr><w:vertAlign w:val="{vert}"/></w:rPr>' if vert else ""
        xml.append(f'<w:r>{rpr}<w:t xml:space="preserve">{x(text)}</w:t></w:r>')
    return "".join(xml)


def formula_para(expr: str, label: str) -> str:
    """Centred formula with its number at the right margin (tab stops)."""
    tabs = '<w:tabs><w:tab w:val="center" w:pos="4535"/><w:tab w:val="right" w:pos="9070"/></w:tabs>'
    label_run = f'<w:r><w:tab/><w:t xml:space="preserve">{x(label)}</w:t></w:r>' if label else ""
    return (f'<w:p><w:pPr><w:pStyle w:val="Formula"/>{tabs}<w:jc w:val="left"/></w:pPr>'
            f'<w:r><w:tab/></w:r>{formula_runs(expr)}{label_run}</w:p>')


def render_items(items: list[Any], number: Numberer) -> list[str]:
    out = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("table"), list):
            out.append(table(item["table"], item.get("caption")))
        elif isinstance(item, dict) and item.get("formula"):
            out.append(formula_para(str(item["formula"]), str(item.get("label") or "")))
        elif isinstance(item, dict):
            for text in as_paragraphs(item):
                out.append(para(number(text)))
        else:
            out.append(para(number(str(item))))
    return out


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as fh:
        header = fh.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not a PNG file: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def fit_extent(w_px: int, h_px: int, max_w_cm: float, max_h_cm: float) -> tuple[int, int]:
    aspect = h_px / w_px if w_px else 1.0
    w_cm = max_w_cm
    h_cm = w_cm * aspect
    if h_cm > max_h_cm:
        h_cm = max_h_cm
        w_cm = h_cm / aspect
    # Do not blow small diagrams up past ~2x their natural 150-dpi size.
    natural_w_cm = w_px / 150 * 2.54
    if natural_w_cm < w_cm and natural_w_cm > 0:
        scale = max(natural_w_cm / w_cm, 0.55)
        w_cm, h_cm = w_cm * scale, h_cm * scale
    return int(w_cm * EMU_PER_CM), int(h_cm * EMU_PER_CM)


class ImageRegistry:
    def __init__(self, embed_svg: bool) -> None:
        self.items: list[dict[str, Any]] = []
        self.embed_svg = embed_svg
        self.doc_pr = 0

    def add(self, png: Path, svg: Path | None) -> dict[str, Any]:
        index = len(self.items) + 1
        item = {"png": png, "svg": svg if (svg and self.embed_svg) else None,
                "rid": f"rIdImg{index}", "target": f"media/image{index}.png"}
        if item["svg"]:
            item["svg_rid"] = f"rIdSvg{index}"
            item["svg_target"] = f"media/image{index}.svg"
        self.items.append(item)
        return item

    def paragraph(self, item: dict[str, Any], max_w_cm: float, max_h_cm: float) -> str:
        self.doc_pr += 1
        w_px, h_px = png_size(item["png"])
        cx, cy = fit_extent(w_px, h_px, max_w_cm, max_h_cm)
        if item.get("svg"):
            blip = (f'<a:blip r:embed="{item["rid"]}"><a:extLst><a:ext uri="{{96DAC541-7B7A-43D3-8B79-37D633B846F1}}">'
                    f'<asvg:svgBlip r:embed="{item["svg_rid"]}"/></a:ext></a:extLst></a:blip>')
        else:
            blip = f'<a:blip r:embed="{item["rid"]}"/>'
        n = self.doc_pr
        return (
            '<w:p><w:pPr><w:pStyle w:val="Figure"/><w:keepNext/><w:jc w:val="center"/></w:pPr><w:r><w:drawing>'
            f'<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
            f'<wp:docPr id="{n}" name="Figure {n}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
            f'<pic:nvPicPr><pic:cNvPr id="{n}" name="Figure {n}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill>{blip}<a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            '</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
        )


def collect_assets(data: dict[str, Any], base_dir: Path, require: bool) -> list[dict[str, Any]]:
    assets = data.get("drawing_assets") if isinstance(data.get("drawing_assets"), list) else []
    result = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        png_raw = str(asset.get("png_path") or "").strip()
        svg_raw = str(asset.get("svg_path") or "").strip()
        png = resolve_path(png_raw, base_dir) if png_raw else None
        svg = resolve_path(svg_raw, base_dir) if svg_raw else None
        if not png or not png.exists():
            raise FileNotFoundError(
                f"图{asset.get('figure_no')}: PNG drawing missing ({png_raw or 'no png_path'}). "
                "Run generate_patent_drawings.py with Pillow and a Chinese font available."
            )
        result.append({"figure_no": int(asset.get("figure_no") or len(result) + 1), "png": png,
                       "svg": svg if svg and svg.exists() else None, "asset": asset})
    result.sort(key=lambda a: a["figure_no"])
    if require and not result:
        raise RuntimeError("No drawing_assets found. Run generate_patent_drawings.py --update-json first.")
    return result


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def application_body(data: dict[str, Any], figures: list[dict[str, Any]], registry: ImageRegistry,
                     number_paragraphs: bool) -> str:
    name = str(data.get("invention_name") or "【待补充：发明名称】").strip()
    parts: list[str] = []

    parts.append(para("说明书摘要", style="PartTitle", align="center"))
    for text in as_paragraphs(data.get("abstract")) or ["【待补充：说明书摘要。】"]:
        parts.append(para(text))

    parts.append(para("摘要附图", style="PartTitle", align="center", page_break=True))
    fig_no = abstract_figure_no(data)
    chosen = next((f for f in figures if f["figure_no"] == fig_no), None)
    if chosen is None and figures:
        chosen = figures[0]
    if chosen:
        item = registry.add(chosen["png"], chosen["svg"])
        parts.append(registry.paragraph(item, ABSTRACT_MAX_W_CM, ABSTRACT_MAX_H_CM))
    else:
        parts.append(para("【待补充：摘要附图。】"))

    parts.append(para("权利要求书", style="PartTitle", align="center", page_break=True))
    for claim in claims_list(data) or ["【待补充：权利要求书。】"]:
        parts.append(para(claim, style="Claim"))

    parts.append(para("说明书", style="PartTitle", align="center", page_break=True))
    parts.append(para(name, style="InventionName", align="center"))
    number = Numberer(number_paragraphs)
    desc = data.get("description") if isinstance(data.get("description"), dict) else {}
    for key, heading in DESCRIPTION_SECTIONS:
        parts.append(para(heading, style="SectionTitle", keep_next=True))
        items = section_items(desc.get(key))
        parts.extend(render_items(items or [f"【待补充：{heading}。】"], number))

    parts.append(para("说明书附图", style="PartTitle", align="center", page_break=True))
    if figures:
        for fig in figures:
            item = registry.add(fig["png"], fig["svg"])
            parts.append(registry.paragraph(item, MAX_W_CM, MAX_H_CM))
            parts.append(para(f"图{fig['figure_no']}", style="FigureLabel", align="center"))
    else:
        parts.append(para("【待补充：说明书附图。】"))
    return "".join(parts)


NOTE_HEADINGS = {
    "source": "来源材料",
    "disclosure_status": "公开状态与新颖性风险",
    "risks": "风险提示",
    "patentability": "可专利性（客体）分析",
    "invention_points": "发明点（区别特征—技术问题—技术效果）",
    "prior_art": "最接近的现有技术",
    "claim_plan": "权利要求布局",
    "next_steps": "后续建议",
}


def claim_tree(claims: list[str]) -> list[str]:
    lines = []
    for i, claim in enumerate(claims, start=1):
        body = re.sub(r"^\s*\d+\s*[\.．、]\s*", "", claim)
        ref = re.match(r"\s*(?:根据|如|按照)权利要求\s*([\d\s或、至到\-～~，,]+?)(?:中任一项|任一项)?所述的?([^，,]{0,30})", body)
        if ref:
            lines.append(f"权利要求{i}：从属于权利要求{ref.group(1).strip()}（{ref.group(2).strip()}）")
        else:
            subject = re.match(r"\s*(.{0,40}?)[，,]\s*其特征", body)
            lines.append(f"权利要求{i}：独立权利要求（{subject.group(1) if subject else body[:30]}）")
    return lines


STANDARD_HANDOVER = [
    ("权属与主体", "申请人、全部发明人及其身份信息；是否属于职务发明（在高校或单位完成的，申请人一般为单位）",
     "请求书必填；发明人信息须真实完整"),
    ("公开情况", "论文、预印本、项目主页、演示、代码、报告的首次公开日期与范围",
     "决定新颖性能否成立及宽限期是否适用"),
    ("现有技术检索", "由专利代理师检索最接近的现有技术，核对权利要求1的区别特征",
     "评估创造性，调整权利要求保护范围"),
]


def handover_rows(data: dict[str, Any]) -> list[list[str]]:
    """Central list of everything the applicant/inventors still need to supply."""
    notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    raw = notes.get("handover")
    rows: list[list[str]] = []
    if isinstance(raw, dict):
        for category, items in raw.items():
            for item in as_paragraphs(items):
                rows.append([str(category), item, ""])
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                rows.append([str(item.get("category") or "其他"), str(item.get("item") or ""), str(item.get("why") or "")])
            else:
                rows.append(["其他", str(item), ""])
    for item in sufficiency_items(data):
        if item["status"] == "gap":
            text = f"{item['feature']}：{item['missing']}" if item["missing"] else item["feature"]
            probe = (item["missing"] or item["feature"])[:8]
            if not any(text[:12] in r[1] or (probe and probe in r[1]) for r in rows):
                where = f"权利要求{item['claim']}" if item["claim"] else "说明书"
                rows.append([f"充分公开（{where}）", text, "说明书需写明具体实现，以支持该权利要求"])
    for gap in as_paragraphs(data.get("gaps")):
        core = re.sub(r"[（(].*?[)）]", "", gap.replace("【待补充：", "").replace("】", "")).strip("。 ")
        if not any(core[:10] in r[1] for r in rows):
            rows.append(["技术细节（正文【待补充】）", gap, "充分公开；支持权利要求"])
    if not str(notes.get("worked_example") or "").strip() and not any("实例" in r[1] for r in rows):
        rows.append(["核心机制实例", "一次真实运行的完整记录：输入 → 各中间产物（结构化记录、规划、冲突与修正前后）→ 最终输出；"
                     "或经发明人确认并标注为示意的实例", "具体实施方式中贯穿全流程的实例，便于理解和支持权利要求"])
    present = {r[0] for r in rows}
    for category, item, why in STANDARD_HANDOVER:
        if category not in present:
            rows.append([category, item, why])
    return rows


def sufficiency_items(data: dict[str, Any]) -> list[dict[str, str]]:
    notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    raw = notes.get("sufficiency")
    items = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status") or "").lower()
            status = "gap" if status in {"gap", "缺失", "待补充", "missing"} else "disclosed"
            items.append({"claim": str(entry.get("claim") or ""), "feature": str(entry.get("feature") or ""),
                          "status": status, "where": str(entry.get("where") or ""),
                          "missing": str(entry.get("missing") or "")})
    return items


def notes_body(data: dict[str, Any], figures: list[dict[str, Any]], check_items: list[dict[str, str]]) -> str:
    name = str(data.get("invention_name") or "").strip()
    parts = [para("撰写说明", style="PartTitle", align="center"),
             para("（本文件不属于专利申请文件，供申请人和专利代理师审核使用，提交前请勿混入申请文件。）", align="center"),
             para(f"发明名称：{name}"),
             para(f"生成日期：{_dt.date.today().isoformat()}"),
             para("本草稿由AI依据所提供的论文材料生成，用于提高撰写效率，不构成法律意见；"
                  "提交前应由专利代理师结合现有技术检索结果审核权利要求的保护范围、新颖性和创造性。")]
    parts.append(para("待补充材料清单（交接）", style="SectionTitle", keep_next=True))
    parts.append(para("以下内容需由申请人或发明人提供、确认后，才能形成可提交的申请文件；正文中的【待补充】占位与本清单一一对应。", keep_next=True))
    parts.append(table([["类别", "需要提供或确认的内容", "用途"]] + handover_rows(data), align="left"))

    audit = sufficiency_items(data)
    if audit:
        parts.append(para("充分公开核查", style="SectionTitle", keep_next=True))
        parts.append(para("逐项核对权利要求特征的数据形式、判定准则、失败处理和参数是否已在说明书中写明。", keep_next=True))
        rows = [["权项", "特征", "状态", "说明书位置/依据", "缺少的内容"]]
        for item in audit:
            rows.append([item["claim"], item["feature"], "已披露" if item["status"] == "disclosed" else "缺失",
                         item["where"], item["missing"]])
        parts.append(table(rows, align="left"))
    worked = str((data.get("notes") or {}).get("worked_example") or "").strip() if isinstance(data.get("notes"), dict) else ""
    if worked:
        parts.append(para(f"核心机制实例来源：{worked}"))

    notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    source_title = str(data.get("source_title") or "").strip()
    if source_title and "source" not in notes:
        notes = {"source": f"论文：{source_title}", **notes}
    for key, value in notes.items():
        if key in {"handover", "sufficiency", "worked_example"}:
            continue
        heading = NOTE_HEADINGS.get(key, key)
        parts.append(para(heading, style="SectionTitle", keep_next=True))
        if isinstance(value, dict):
            for k, v in value.items():
                parts.append(para(f"{k}：{'；'.join(as_paragraphs(v))}"))
        else:
            for text in as_paragraphs(value):
                parts.append(para(text))

    claims = claims_list(data)
    if claims and "claim_plan" not in notes:
        parts.append(para("权利要求结构", style="SectionTitle", keep_next=True))
        for line in claim_tree(claims):
            parts.append(para(line))

    support = data.get("support_map")
    if isinstance(support, dict) and support:
        parts.append(para("权利要求—论文出处对照", style="SectionTitle", keep_next=True))
        rows = [["权利要求", "论文出处"]]
        for key in sorted(support, key=lambda k: int(re.sub(r"\D", "", str(k)) or 0)):
            rows.append([str(key), "；".join(as_paragraphs(support[key]))])
        parts.append(table(rows, align="left"))

    if figures:
        parts.append(para("附图来源与精修提示词", style="SectionTitle", keep_next=True))
        for fig in figures:
            asset = fig["asset"]
            title = asset.get("title") or ""
            source = asset.get("source") or "未注明"
            parts.append(para(f"图{fig['figure_no']}　{title}；来源：{source}"))
            prompt = asset.get("image_model_prompt")
            if prompt:
                parts.append(para(f"图像模型精修提示词：{prompt}", style="Small"))

    parts.append(para("自动检查结果", style="SectionTitle", keep_next=True))
    if check_items:
        for item in check_items:
            parts.append(para(f"[{item['level']}] {item['where']}：{item['message']}", style="Small"))
    else:
        parts.append(para("未发现格式问题。"))
    return "".join(parts)


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体" w:cs="Times New Roman"/>
<w:sz w:val="24"/><w:szCs w:val="24"/><w:lang w:val="en-US" w:eastAsia="zh-CN"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="0" w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
<w:style w:type="paragraph" w:styleId="Body"><w:name w:val="Patent Body"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:ind w:firstLineChars="200" w:firstLine="480"/><w:jc w:val="both"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Claim"><w:name w:val="Patent Claim"/><w:basedOn w:val="Body"/><w:pPr><w:spacing w:after="60"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="PartTitle"><w:name w:val="Part Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="120" w:after="240"/><w:jc w:val="center"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="黑体"/><w:b/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="InventionName"><w:name w:val="Invention Name"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="200"/><w:jc w:val="center"/></w:pPr><w:rPr><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="SectionTitle"><w:name w:val="Section Title"/><w:basedOn w:val="Normal"/><w:qFormat/>
<w:pPr><w:keepNext/><w:spacing w:before="160" w:after="60"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="黑体"/><w:b/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Figure"><w:name w:val="Figure"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="60" w:line="240" w:lineRule="auto"/><w:jc w:val="center"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="FigureLabel"><w:name w:val="Figure Label"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="240"/><w:jc w:val="center"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Formula"><w:name w:val="Formula"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="60" w:after="60"/><w:jc w:val="center"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="TableCaption"><w:name w:val="Table Caption"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:jc w:val="center"/></w:pPr><w:rPr><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Small"><w:name w:val="Small"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="40" w:line="280" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Footer"><w:name w:val="footer"/><w:basedOn w:val="Normal"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:sz w:val="18"/></w:rPr></w:style>
</w:styles>
"""

FOOTER = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:pPr><w:pStyle w:val="Footer"/><w:jc w:val="center"/></w:pPr>
<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r>
</w:p></w:ftr>
"""


def write_package(path: Path, body: str, registry: ImageRegistry, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sect = ('<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/>'
            '<w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1418" w:bottom="1440" w:left="1418" w:header="851" w:footer="851" w:gutter="0"/>'
            '</w:sectPr>')
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}>'
                f"<w:body>{body}{sect}</w:body></w:document>")
    rels = ['<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
            '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>']
    for item in registry.items:
        rels.append(f'<Relationship Id="{item["rid"]}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{item["target"]}"/>')
        if item.get("svg"):
            rels.append(f'<Relationship Id="{item["svg_rid"]}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{item["svg_target"]}"/>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="svg" ContentType="image/svg+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        "</Relationships>"
    )
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>{x(title)}</dc:title><dc:creator>paper2patent</dc:creator></cp:coreProperties>"
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", package_rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("word/document.xml", document)
        zf.writestr("word/styles.xml", STYLES)
        zf.writestr("word/footer1.xml", FOOTER)
        zf.writestr("word/_rels/document.xml.rels",
                    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    + "".join(rels) + "</Relationships>")
        for item in registry.items:
            zf.write(item["png"], f"word/{item['target']}")
            if item.get("svg"):
                zf.write(item["svg"], f"word/{item['svg_target']}")


def run_checker(data: dict[str, Any]) -> list[dict[str, str]]:
    try:
        from check_patent_draft import run_checks
    except ImportError:  # pragma: no cover
        return []
    import copy
    return run_checks(copy.deepcopy(data)).items


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a Chinese patent application DOCX from JSON.")
    parser.add_argument("input", type=Path, help="Patent content JSON (after generate_patent_drawings.py --update-json).")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Application DOCX path.")
    parser.add_argument("--notes-output", type=Path, help="Drafting-notes DOCX path (default: <output>_撰写说明.docx).")
    parser.add_argument("--no-notes", action="store_true", help="Do not write the drafting-notes DOCX.")
    parser.add_argument("--require-drawings", action="store_true", help="Fail if no drawing assets are available.")
    parser.add_argument("--number-paragraphs", action="store_true", help="Prefix description paragraphs with [0001] numbers.")
    parser.add_argument("--embed-svg", action="store_true", help="Also embed SVG (Word 2016+ shows vector, others use PNG).")
    args = parser.parse_args()

    data = read_json(args.input)
    base_dir = args.input.parent
    try:
        figures = collect_assets(data, base_dir, args.require_drawings)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    registry = ImageRegistry(embed_svg=args.embed_svg)
    body = application_body(data, figures, registry, args.number_paragraphs)
    title = str(data.get("invention_name") or "专利申请文件")
    write_package(args.output, body, registry, title)
    print(f"Wrote {args.output} ({args.output.stat().st_size} bytes, figures={len(figures)})")

    if not args.no_notes:
        notes_path = args.notes_output or args.output.with_name(args.output.stem + "_撰写说明.docx")
        check_items = run_checker(data)
        notes_registry = ImageRegistry(embed_svg=False)
        write_package(notes_path, notes_body(data, figures, check_items), notes_registry, f"{title}（撰写说明）")
        errors = sum(1 for i in check_items if i["level"] == "ERROR")
        print(f"Wrote {notes_path} (check: {errors} errors, {len(check_items) - errors} warnings/info)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
