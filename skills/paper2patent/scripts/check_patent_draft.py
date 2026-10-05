#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mechanical checks for a Chinese invention patent draft (patent content JSON).

Catches the formal defects that examiners and agents reject most often and
that a language model tends to miss when reviewing its own text:

- claim numbering, single final period, uncertain words, references to the
  description or figures inside claims;
- dependent-claim references (only earlier claims, 择一 for multiple
  dependency, no multiple-dependent claim based on another one), matching
  subject names, and a heuristic antecedent-basis check for "所述X";
- invention name length and consistency, abstract length (300 characters
  including punctuation), commercial or self-praising language;
- description completeness, figure numbering consistency between 附图说明,
  drawings and the abstract figure, step numbers used in drawings but never
  explained in the description;
- leftover 【待补充】 placeholders, missing claim-to-source support entries;
- scope heuristics: code identifiers or negative limitations in claims,
  long enumerations or excessive length in claim 1, a revision/iteration
  mechanism in the claims that no drawing shows as a loop or decision,
  dependent claims that bundle several mechanisms, absolute wording beyond
  the evidence, drafting-process remarks inside the description, and a
  missing sufficiency audit (notes.sufficiency).

Usage:
    python check_patent_draft.py patent_content.json [--json report.json]

Exit code 1 when any ERROR is found, otherwise 0. Warnings need a human or
model judgement; they are not automatically wrong.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patent_common import (  # noqa: E402
    DESCRIPTION_SECTIONS,
    FIGURE_NO_RE,
    abstract_figure_no,
    as_paragraphs,
    claims_list,
    normalize_drawings,
    read_json,
    visible_len,
)

# Uncertain / non-limiting wording that makes a claim unclear (专利审查指南
# 第二部分第二章 3.2.2 plus common agency style rules). Each entry is a regex.
CLAIM_FORBIDDEN = [
    (r"(?<![相均对平不])等(?![于同价效式距比差长分级待候])", "等"),
    (r"大约|约为|约(?=\d)|左右(?=[，。；、]|$)|(?<=\d)左右", "约/大约/左右"),
    (r"可以|可能|也许|或许", "可以/可能"),
    (r"例如|比如|诸如|譬如", "例如/比如"),
    (r"优选|最好是|最好地|尤其是|特别是", "优选/最好是/尤其是"),
    (r"必要时|如有必要|视情况", "必要时"),
    (r"(?<!最)接近|近似于|或类似物|类似的", "接近/或类似物"),  # 最接近 (closest) is definite
    (r"不限于|包括但不限于", "不限于"),
    (r"若干|某些|一些|某种程度上|基本上", "若干/某些/基本上"),
    (r"如说明书|如图\s*\d|如附图|参见图", "引用说明书/附图"),
    (r"本文|本论文|论文|作者|我们", "论文化用语"),
]
SPEC_FORBIDDEN = [
    (r"如权利要求\s*\d+\s*(?:至\s*\d+\s*)?(?:中任一项)?所述", "说明书中使用'如权利要求……所述'引用语"),
    (r"本文|本论文|该论文|这篇论文|我们提出|我们的|本工作|作者", "论文化用语（应改为'本发明/本实施例'）"),
]
# Drafting-process remarks that belong in the drafting notes, not the description.
META_COMMENTARY = (r"论文中|论文未|论文给出|论文所述|根据论文|依据论文|原论文|原文中|本草稿|本稿|初稿编制|编稿|撰写时|"
                   r"生成过程|未补入|不补造|未补造|未自行|独立运行|skill")
# Technical clarifications ("该约束针对任务指令长度，而非音乐长度"; "修正回路并不表示重做全部模态处理")
# are wanted in the description and are deliberately not matched here.
ABSOLUTE_RE = re.compile(r"保证|必然|彻底|杜绝|完全避免|一切|绝对|百分之百|从根本上|始终能够|万无一失")
COMMERCIAL = r"最先进|最佳|最好的|世界领先|国际领先|国内领先|领先水平|革命性|颠覆性|首创|独一无二|完美|极大地|划时代|顶级|SOTA|state-of-the-art"

NAME_MAX = 25
ABSTRACT_MAX = 300
CLAIM_FEE_THRESHOLD = 10

CLAIM_NO_RE = re.compile(r"^\s*(\d+)\s*[\.．、]\s*")
REF_RE = re.compile(r"(?:根据|如)权利要求\s*(\d+)(?:\s*(?:或|、|至|到|-|～|~)\s*(\d+))*")
REF_ALL_NUMS_RE = re.compile(r"权利要求\s*([\d\s或、至到\-～~，,]+?)(?:中任一项|中任意一项|任一项)?所述")
SUBJECT_RE = re.compile(r"所述的?([^，,：:；;]{1,40}?)[，,]\s*其特征")


class Report:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, level: str, code: str, where: str, message: str) -> None:
        self.items.append({"level": level, "code": code, "where": where, "message": message})

    def error(self, code: str, where: str, message: str) -> None:
        self.add("ERROR", code, where, message)

    def warn(self, code: str, where: str, message: str) -> None:
        self.add("WARN", code, where, message)

    def info(self, code: str, where: str, message: str) -> None:
        self.add("INFO", code, where, message)

    @property
    def errors(self) -> int:
        return sum(1 for i in self.items if i["level"] == "ERROR")

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.items if i["level"] == "WARN")


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

def parse_references(text: str) -> list[int]:
    """Return claim numbers referenced by a dependent claim (expands ranges)."""
    head = text[:120]
    match = REF_ALL_NUMS_RE.search(head)
    if not match:
        match_simple = REF_RE.search(head)
        return [int(match_simple.group(1))] if match_simple else []
    expr = match.group(1)
    nums: list[int] = []
    for part in re.split(r"[或、，,]", expr):
        part = part.strip()
        if not part:
            continue
        rng = re.split(r"\s*(?:至|到|-|～|~)\s*", part)
        if len(rng) == 2 and rng[0].isdigit() and rng[1].isdigit():
            a, b = int(rng[0]), int(rng[1])
            nums.extend(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            nums.append(int(part))
    return nums


def claim_subject(text: str, is_dependent: bool) -> str:
    body = CLAIM_NO_RE.sub("", text, count=1)
    if is_dependent:
        match = SUBJECT_RE.search(body[:160])
        return match.group(1).strip() if match else ""
    match = re.match(r"\s*(?:一种|一个)?(.+?)[，,]\s*其特征", body)
    return match.group(1).strip() if match else ""


def category(subject: str) -> str:
    for word in ("存储介质", "程序产品", "电子设备", "设备", "装置", "系统", "终端", "芯片", "方法"):
        if subject.endswith(word) or word in subject[-8:]:
            return word
    return subject[-4:]


def antecedent_terms(text: str) -> list[str]:
    terms = []
    for match in re.finditer(r"所述(?:的)?([一-鿿A-Za-z0-9]{2,16})", text):
        term = match.group(1)
        term = re.split(r"(?:包括|包含|进行|通过|根据|基于|采用|利用|对|将|为|是|与|和|及|中|的|在|由|从|经|被|按照|得到|生成|确定|输入|输出|可以|可|还|具体|分别|作为|用于|以|并|再|即|满足|大于|小于|等于|不小于|不大于)", term, maxsplit=1)[0]
        if len(term) >= 2:
            terms.append(term)
    return terms


def check_claims(data: dict[str, Any], report: Report) -> list[str]:
    claims = claims_list(data)
    if not claims:
        report.error("C00", "权利要求书", "没有权利要求。")
        return []
    if len(claims) > CLAIM_FEE_THRESHOLD:
        report.info("C01", "权利要求书", f"共{len(claims)}项权利要求；超过10项的部分每项需缴权利要求附加费。")

    texts: dict[int, str] = {}
    independent: list[int] = []
    multi: set[int] = set()
    parents: dict[int, list[int]] = {}
    for i, raw in enumerate(claims, start=1):
        where = f"权利要求{i}"
        m = CLAIM_NO_RE.match(raw)
        if not m:
            report.error("C02", where, "缺少阿拉伯数字编号（应为“1.”格式开头）。")
        elif int(m.group(1)) != i:
            report.error("C02", where, f"编号为{m.group(1)}，应顺序编号为{i}。")
        body = CLAIM_NO_RE.sub("", raw, count=1).strip()
        texts[i] = body
        periods = body.count("。")
        if not body.endswith("。"):
            report.error("C03", where, "权利要求应以句号结尾。")
        if periods > 1 or (periods == 1 and not body.endswith("。")):
            report.error("C03", where, "权利要求中间出现句号；每项权利要求只允许结尾一个句号。")
        if "其特征" not in body:
            report.warn("C04", where, "未使用“其特征在于”划分前序部分与特征部分。")
        for pattern, label in CLAIM_FORBIDDEN:
            for hit in re.finditer(pattern, body):
                snippet = body[max(0, hit.start() - 8): hit.end() + 8]
                level = "ERROR" if label not in {"若干/某些/基本上"} else "WARN"
                report.add(level, "C05", where, f"不确定/不当用语“{hit.group(0)}”（{label}）：…{snippet}…")
        if re.search(r"[（(]\s*(?:见|参见)?图", body):
            report.warn("C06", where, "括号内引用附图；权利要求中只可在技术特征后括注附图标记数字。")
        if re.search(COMMERCIAL, body, flags=re.IGNORECASE):
            report.error("C07", where, "权利要求中出现宣传性用语。")

        refs = parse_references(body) if re.match(r"\s*(?:根据|如|按照)权利要求", body) else []
        if refs:
            parents[i] = refs
            if any(r >= i for r in refs):
                report.error("C10", where, f"引用了在后或自身的权利要求{refs}；从属权利要求只能引用在前的权利要求。")
            if len(set(refs)) > 1:
                multi.add(i)
                if not re.search(r"或|任一项|任意一项", body[:120]):
                    report.error("C11", where, "多项从属权利要求应以择一方式引用（“或”/“中任一项”）。")
        else:
            independent.append(i)
            embedded = parse_references(body)
            if embedded and any(r >= i for r in embedded):
                report.error("C10", where, "引用了在后或自身的权利要求。")

    for i, refs in parents.items():
        if i in multi:
            for r in refs:
                if r in multi:
                    report.error("C12", f"权利要求{i}", f"多项从属权利要求不得作为另一项多项从属权利要求的引用基础（引用了权利要求{r}）。")

    # Subject names and categories.
    subjects = {i: claim_subject(texts[i], i in parents) for i in texts}
    for i, refs in parents.items():
        own = subjects.get(i, "")
        for r in refs:
            if r not in subjects or r >= i:
                continue
            parent_subject = subjects[r]
            if own and parent_subject and category(own) != category(parent_subject):
                report.error("C13", f"权利要求{i}", f"主题“{own}”与被引用的权利要求{r}的主题“{parent_subject}”类型不一致。")
            elif own and parent_subject and own not in parent_subject and parent_subject not in own:
                report.warn("C13", f"权利要求{i}", f"主题名称“{own}”与权利要求{r}的“{parent_subject}”不一致。")

    # Antecedent basis (heuristic).
    def ancestry_text(i: int, seen: set[int] | None = None) -> str:
        seen = seen or set()
        if i in seen:
            return ""
        seen.add(i)
        text = texts.get(i, "")
        for r in parents.get(i, []):
            if r < i:
                text += "\n" + ancestry_text(r, seen)
        return text

    particles = set("的包进通根基采利对将为是与和及中在由从经被按得生确输可还具分作用以并再即满大小等不时后前内上下之所")
    for i, body in texts.items():
        for match in re.finditer(r"所述(?:的)?", body):
            before = body[: match.start()]
            if re.search(r"(?:权利要求\s*\d+|任一项|任意一项|之一)\s*$", before):
                continue  # "权利要求1所述的…" is a reference, not an antecedent use
            captured_match = re.match(r"([\u4e00-\u9fffA-Za-z0-9]{2,16})", body[match.end():])
            if not captured_match:
                continue
            captured = captured_match.group(1)
            context = (before + "\n" + "\n".join(ancestry_text(r) for r in parents.get(i, [])))
            context = context.replace("其特征在于", "").replace("其特征是", "")
            longest = 0
            for size in range(len(captured), 1, -1):
                if captured[:size] in context:
                    longest = size
                    break
            threshold = 2 if (len(captured) == 2 or captured[2] in particles) else 3
            if longest < threshold:
                shown = (antecedent_terms("所述" + captured) or [captured])[0]
                report.warn("C14", f"权利要求{i}", f"“所述{shown}”在本权利要求前文及其引用的权利要求中找不到引用基础。")

    if not independent:
        report.error("C15", "权利要求书", "没有独立权利要求。")
    elif independent[0] != 1:
        report.error("C15", "权利要求书", "权利要求1应为独立权利要求。")
    data["_independent_claims"] = independent
    return claims


# ---------------------------------------------------------------------------
# Name / abstract / description
# ---------------------------------------------------------------------------

def check_name_and_abstract(data: dict[str, Any], claims: list[str], report: Report) -> None:
    name = str(data.get("invention_name") or "").strip()
    if not name:
        report.error("N01", "发明名称", "缺少发明名称。")
    else:
        core = re.sub(r"^一种", "", name)
        if visible_len(core) > NAME_MAX:
            report.warn("N02", "发明名称", f"发明名称{visible_len(core)}字，一般不超过{NAME_MAX}字。")
        if re.search(r"[A-Za-z]{2,}", core):
            report.warn("N03", "发明名称", "发明名称含英文/型号/商品名，一般应使用中文技术术语。")
        if re.search(COMMERCIAL, core, flags=re.IGNORECASE):
            report.error("N04", "发明名称", "发明名称含宣传用语。")
        if claims:
            first = CLAIM_NO_RE.sub("", claims[0], count=1)
            first_subject = claim_subject(first, False)
            key = re.split(r"[、及和与]", core)[0]
            key = re.sub(r"(方法|装置|系统|设备)$", "", key)
            if key and key[:4] not in first:
                report.warn("N05", "权利要求1", f"权利要求1主题“{first_subject}”未体现发明名称“{name}”。")

    abstract = " ".join(as_paragraphs(data.get("abstract")))
    if not abstract:
        report.error("A01", "说明书摘要", "缺少说明书摘要。")
        return
    length = visible_len(abstract)
    if length > ABSTRACT_MAX:
        report.error("A02", "说明书摘要", f"摘要{length}字（含标点），超过{ABSTRACT_MAX}字。")
    if name:
        core = re.sub(r"^一种", "", name)
        head = re.split(r"[、及]", core)[0]
        if head[:6] not in abstract:
            report.warn("A03", "说明书摘要", "摘要未写明发明名称。")
    if re.search(COMMERCIAL, abstract, flags=re.IGNORECASE):
        report.error("A04", "说明书摘要", "摘要含商业性宣传用语。")
    if len(as_paragraphs(data.get("abstract"))) > 1:
        report.warn("A05", "说明书摘要", "摘要一般写成一段。")


def check_description(data: dict[str, Any], report: Report) -> None:
    desc = data.get("description")
    if not isinstance(desc, dict):
        report.error("D01", "说明书", "description 应为包含五个部分的对象。")
        return
    for key, heading in DESCRIPTION_SECTIONS:
        if not as_paragraphs(desc.get(key)):
            report.error("D02", f"说明书/{heading}", "该部分为空。")
    full = "\n".join(as_paragraphs(desc))
    for pattern, label in SPEC_FORBIDDEN:
        for hit in re.finditer(pattern, full):
            snippet = full[max(0, hit.start() - 10): hit.end() + 10].replace("\n", " ")
            report.warn("D03", "说明书", f"{label}：…{snippet}…")
            break
    if re.search(COMMERCIAL, full, flags=re.IGNORECASE):
        hit = re.search(COMMERCIAL, full, flags=re.IGNORECASE)
        report.warn("D04", "说明书", f"出现宣传性用语“{hit.group(0)}”。")
    meta = sorted({m.group(0) for m in re.finditer(META_COMMENTARY, full, flags=re.IGNORECASE)})
    if meta:
        hit = re.search(META_COMMENTARY, full, flags=re.IGNORECASE)
        snippet = full[max(0, hit.start() - 15): hit.end() + 15].replace("\n", " ")
        report.warn("D08", "说明书", f"疑似撰写过程说明或对论文的引用（{'、'.join(meta)}）：…{snippet}…；"
                    "技术正文只保留理解方案所需的内容和真实的证据边界，其余移入撰写说明（notes）。")
    embodiments = "\n".join(as_paragraphs(desc.get("embodiments")))
    if embodiments and len(re.sub(r"\s", "", embodiments)) < 1500:
        report.warn("D05", "说明书/具体实施方式", "具体实施方式偏短（<1500字），可能不足以支持权利要求或充分公开。")
    background = "\n".join(as_paragraphs(desc.get("background")))
    if background and not re.search(r"问题|缺陷|不足|难以|无法|局限", background):
        report.warn("D06", "说明书/背景技术", "背景技术未写明现有技术存在的问题。")
    content = "\n".join(as_paragraphs(desc.get("invention_content")))
    if content and not re.search(r"有益效果|技术效果|能够|从而", content):
        report.warn("D07", "说明书/发明内容", "发明内容未说明有益效果。")


def check_figures(data: dict[str, Any], report: Report) -> None:
    desc = data.get("description") if isinstance(data.get("description"), dict) else {}
    drawing_desc = "\n".join(as_paragraphs(desc.get("drawing_description")))
    described = sorted({int(n) for n in FIGURE_NO_RE.findall(drawing_desc)})
    figures, legacy_warnings = normalize_drawings(data)
    drawn = sorted(f["figure_no"] for f in figures)
    for w in legacy_warnings:
        report.warn("F00", "说明书附图", w)
    if drawn and drawn != list(range(1, len(drawn) + 1)):
        report.error("F01", "说明书附图", f"附图编号应为图1、图2……连续编号，当前为{drawn}。")
    if described and drawn and described != drawn:
        report.error("F02", "附图说明", f"附图说明中的图号{described}与说明书附图{drawn}不一致。")
    if drawn and not described:
        report.error("F02", "附图说明", "有说明书附图但附图说明未逐图说明。")
    fig_no = abstract_figure_no(data)
    if drawn:
        if fig_no is None:
            report.warn("F03", "摘要附图", "未指定摘要附图（abstract_figure）。")
        elif fig_no not in drawn:
            report.error("F03", "摘要附图", f"指定的摘要附图图{fig_no}不存在。")
    embodiments = "\n".join(as_paragraphs(desc.get("embodiments")))
    for n in drawn:
        if embodiments and f"图{n}" not in re.sub(r"\s", "", embodiments):
            report.warn("F04", f"图{n}", "具体实施方式中没有结合该附图进行说明。")
    full_desc = "\n".join(as_paragraphs(desc))
    for fig in figures:
        n = fig["figure_no"]
        node_ids = {node["id"] for node in fig.get("nodes", [])}
        for edge in fig.get("edges", []):
            if edge["from"] not in node_ids or edge["to"] not in node_ids:
                report.error("F05", f"图{n}", f"连线{edge['from']}→{edge['to']}引用了不存在的节点。")
        for node in fig.get("nodes", []):
            label = node.get("label", "")
            if FIGURE_NO_RE.search(label):
                report.error("F06", f"图{n}", f"节点“{label}”中含图号；图号只能写在附图下方。")
            for step in re.findall(r"S\d{2,4}", label):
                if step not in full_desc:
                    report.warn("F07", f"图{n}", f"步骤编号{step}未在说明书中出现。")
            if node.get("ref") and str(node["ref"]) not in full_desc:
                report.error("F08", f"图{n}", f"附图标记{node['ref']}未在说明书文字部分出现（实施细则第二十一条）。")
        if fig.get("container", {}) and isinstance(fig.get("container"), dict) and fig["container"].get("ref"):
            ref = str(fig["container"]["ref"])
            if ref not in full_desc:
                report.error("F08", f"图{n}", f"附图标记{ref}未在说明书文字部分出现。")
        if len(fig.get("nodes", [])) > 1 and not fig.get("edges"):
            report.warn("F09", f"图{n}", "附图没有任何连接关系；请按论文原图或说明书补充明确的连线。")


def check_support_and_gaps(data: dict[str, Any], claims: list[str], report: Report) -> None:
    support = data.get("support_map")
    if not isinstance(support, dict) or not support:
        report.warn("S01", "support_map", "未提供权利要求-论文出处对照（support_map）；无法追溯忠实性。")
    else:
        for i in range(1, len(claims) + 1):
            refs = support.get(str(i)) or support.get(i)
            if not refs:
                report.warn("S02", f"权利要求{i}", "support_map 中缺少该权利要求的论文出处。")
    all_text = json.dumps({k: data.get(k) for k in ("abstract", "claims", "description")}, ensure_ascii=False)
    placeholders = re.findall(r"【待补充[^】]*】", all_text)
    gaps = as_paragraphs(data.get("gaps"))
    if placeholders:
        report.info("G01", "全文", f"仍有{len(placeholders)}处【待补充】占位，需由申请人补充材料。")
        if not gaps:
            report.error("G02", "gaps", "正文有【待补充】占位，但 gaps 列表为空。")
    abstract_claims = "\n".join(claims)
    if "【待补充" in abstract_claims:
        report.warn("G03", "权利要求书", "权利要求中含【待补充】占位，提交前必须替换。")


# Code identifiers (gt_lyric, auto_prompt_audio_type, promptType, `idx`), but not
# math variables with subscripts (x_pkg, s_j, p_teacher), which claims may use.
CODE_IDENT_RE = re.compile(
    r"`[^`]+`"
    r"|(?<![A-Za-z0-9_])[a-z]{2,}[a-z0-9]*(?:_[a-z0-9]+)+(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_])[a-z]+(?:_[a-z0-9]+){2,}(?![A-Za-z0-9_])"
    r"|(?<![A-Za-z0-9_])[a-z]+[A-Z][A-Za-z0-9]+(?![A-Za-z0-9_])"
)
NEGATIVE_RE = re.compile(r"不包括|不包含|不含有?|不设置|不设有|不具有|无需|省略|不采用|不使用|不存在")
LOOP_TEXT_RE = re.compile(r"修订|重试|重新生成|重新执行|迭代|循环|返回至|返回到|直至|直到|未通过|轮数|收敛|重复执行")


def check_claim_scope(data: dict[str, Any], claims: list[str], report: Report) -> None:
    """Heuristics for over-narrow or implementation-bound claims (warnings only)."""
    if not claims:
        return
    for i, raw in enumerate(claims, start=1):
        body = CLAIM_NO_RE.sub("", raw, count=1)
        idents = sorted({m.group(0) for m in CODE_IDENT_RE.finditer(body)})
        if idents:
            report.warn("C20", f"权利要求{i}", f"出现代码字段/变量名（{'、'.join(idents[:4])}）；权利要求宜写其技术含义，"
                        "具体字段名放到具体实施方式。")
        for hit in NEGATIVE_RE.finditer(body):
            before, after = body[max(0, hit.start() - 25): hit.start()], body[hit.end(): hit.end() + 30]
            if re.search(r"当|若|如果|在[^，；]*情况下", before) and re.search(r"时|情况下", after):
                continue  # a condition ("当……不包括视频时"), not a negative limitation
            snippet = body[max(0, hit.start() - 10): hit.end() + 12]
            report.warn("C21", f"权利要求{i}", f"否定性限定“{hit.group(0)}”：…{snippet}…；只有当“不具备该特征”本身是"
                        "论文所述的技术贡献时才写入权利要求，否则放在实施方式中说明。")
            break
    first = CLAIM_NO_RE.sub("", claims[0], count=1)
    length = visible_len(first)
    if length > 600:
        report.warn("C23", "权利要求1", f"共{length}字。较长的独立权利要求往往写入了实施例层面的细节；请逐项确认每个特征"
                    "都是解决技术问题所必需的，其余移入从属权利要求。")
    for segment in re.split(r"[，,；;：:。]", first):
        items = segment.count("、")
        if re.search(r"至少一|任一|任意一|之一|或者|其中一", segment):
            continue  # alternatives broaden the claim; they do not add limitations
        if items >= 3:
            report.warn("C22", "权利要求1", f"含{items + 1}项并列列举：“{segment[:40]}…”；确认每一项都是必要技术特征，"
                        "否则在权利要求1中保留上位表述，把完整列举移入从属权利要求。")


def check_dependent_granularity(claims: list[str], report: Report) -> None:
    """Warn when a dependent claim seems to bundle several separable mechanisms."""
    for i, raw in enumerate(claims, start=1):
        body = CLAIM_NO_RE.sub("", raw, count=1)
        if not re.match(r"\s*(?:根据|如|按照)权利要求", body):
            continue
        feature = body.split("其特征在于", 1)[-1]
        clauses = [c for c in re.split(r"；|;", feature) if len(re.sub(r"\s", "", c)) > 15]
        if len(clauses) >= 4 and visible_len(feature) > 300:
            report.warn("C24", f"权利要求{i}", f"含{len(clauses)}个较长的并列子句（{visible_len(feature)}字），可能合并了多个可分别作为"
                        "后备的机制；若各子机制能各自解决问题，拆成多项从属权利要求（可相互引用形成层次）。")


def check_strength(data: dict[str, Any], claims: list[str], report: Report) -> None:
    """Absolute wording must be backed by the paper's evidence."""
    for i, raw in enumerate(claims, start=1):
        hit = ABSOLUTE_RE.search(raw)
        if hit:
            report.warn("C25", f"权利要求{i}", f"绝对化措辞“{hit.group(0)}”；保持论文原有的强度（如“要求……通过检查后才接受”），"
                        "不要写成“保证/杜绝”，除非论文有直接证据。")
    desc = data.get("description") if isinstance(data.get("description"), dict) else {}
    effects = "\n".join(as_paragraphs(desc.get("invention_content")))
    hits = sorted({m.group(0) for m in ABSOLUTE_RE.finditer(effects)})
    if hits:
        report.warn("C25", "说明书/发明内容", f"有益效果中出现绝对化措辞（{'、'.join(hits)}），请核对论文证据强度。")


def check_sufficiency_audit(data: dict[str, Any], report: Report) -> None:
    notes = data.get("notes") if isinstance(data.get("notes"), dict) else {}
    audit = notes.get("sufficiency")
    if not isinstance(audit, list) or not audit:
        report.warn("S03", "notes.sufficiency", "未做充分公开核查：请对权利要求1及主要从属权利要求的每个特征，核对输入输出形式、判定准则、"
                    "失败处理和参数是否已在说明书中写明，缺失项进入交接清单。")
        return
    for item in audit:
        if isinstance(item, dict) and str(item.get("status", "")).lower() in {"gap", "缺失", "待补充"} and not item.get("missing"):
            report.warn("S04", "notes.sufficiency", f"核查项“{str(item.get('feature', ''))[:20]}”标为缺失，但未写明缺少什么。")


def has_loop_or_decision(fig: dict[str, Any]) -> bool:
    if any(str(n.get("shape")) == "decision" for n in fig.get("nodes", [])):
        return True
    adjacency: dict[str, list[str]] = {}
    for edge in fig.get("edges", []):
        adjacency.setdefault(edge["from"], []).append(edge["to"])
    state: dict[str, int] = {}

    def dfs(u: str) -> bool:
        state[u] = 1
        for v in adjacency.get(u, []):
            if state.get(v) == 1 or (not state.get(v) and dfs(v)):
                return True
        state[u] = 2
        return False

    return any(not state.get(u) and dfs(u) for u in list(adjacency))


def check_mechanism_drawn(data: dict[str, Any], claims: list[str], report: Report) -> None:
    figures, _ = normalize_drawings(data)
    if not figures:
        return
    text = "\n".join(claims)
    hit = LOOP_TEXT_RE.search(text)
    if hit and not any(has_loop_or_decision(f) for f in figures):
        report.warn("F10", "说明书附图", f"权利要求中有校验/修订/迭代类机制（“{hit.group(0)}”），但附图中没有判断框或回环。"
                    "请在流程图中画出失败返回、重试或依赖复核路径，不要只画成功时的线性主路径。")


def run_checks(data: dict[str, Any]) -> Report:
    report = Report()
    claims = check_claims(data, report)
    check_name_and_abstract(data, claims, report)
    check_description(data, report)
    check_figures(data, report)
    check_support_and_gaps(data, claims, report)
    check_claim_scope(data, claims, report)
    check_dependent_granularity(claims, report)
    check_strength(data, claims, report)
    check_mechanism_drawn(data, claims, report)
    check_sufficiency_audit(data, report)
    data.pop("_independent_claims", None)
    return report


def format_report(report: Report) -> str:
    lines = [f"检查结果：{report.errors} 个错误，{report.warnings} 个警告"]
    for level in ("ERROR", "WARN", "INFO"):
        for item in report.items:
            if item["level"] == level:
                lines.append(f"[{level}] {item['code']} {item['where']}: {item['message']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a patent content JSON for formal defects.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--json", type=Path, help="Also write the report as JSON.")
    args = parser.parse_args()
    try:
        data = read_json(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read {args.input}: {exc}", file=sys.stderr)
        return 2
    report = run_checks(data)
    print(format_report(report))
    if args.json:
        args.json.write_text(json.dumps({"errors": report.errors, "warnings": report.warnings, "items": report.items},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
