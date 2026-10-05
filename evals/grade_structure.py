#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Structural assertions for one or more paper2patent runs.

Each run directory must contain the run's files (any depth): the patent
content JSON, the application DOCX, the 撰写说明 DOCX, and final_message.md.
Writes grading.json into each run directory and prints a summary.

These checks cover form and structure only (clean application file, claim
layout, checker errors, handover list, drawings produced by the bundled
scripts, unsupported numbers). Quality of claim scope, sufficiency and
fidelity needs the rubric in rubric.md and a blind comparison.

Usage:
    python evals/grade_structure.py --source inputs/paper.txt RUN_DIR [RUN_DIR ...]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "skills" / "paper2patent" / "scripts"))
from check_patent_draft import run_checks  # noqa: E402


def docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    paras = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S):
        text = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, flags=re.S)).strip()
        paras.append(text if text else ("[IMG]" if "<w:drawing" in p else ""))
    return paras


def pick(run: Path, pattern: str, exclude: str | None = None) -> Path | None:
    hits = [p for p in run.rglob(pattern) if "preview" not in p.parts]
    if exclude:
        hits = [p for p in hits if exclude not in p.name]
    return sorted(hits, key=lambda p: (len(p.parts), len(p.name)))[0] if hits else None


def numbers(text: str) -> set[str]:
    found = set(re.findall(r"\d+(?:\.\d+)?", text))
    for mant, exp in re.findall(r"(\d+(?:\.\d+)?)e-(\d+)", text):
        found.add(format(float(mant) * 10 ** -int(exp), "f").rstrip("0").rstrip("."))
    return found


def grade(run: Path, source_text: str) -> dict:
    results = []

    def add(text: str, passed: bool, evidence: str) -> None:
        results.append({"text": text, "passed": bool(passed), "evidence": evidence})

    app = pick(run, "*.docx", exclude="撰写说明")
    notes_doc = pick(run, "*撰写说明*.docx")
    pdf = pick(run, "*.pdf")
    content = None
    for candidate in run.rglob("*.json"):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError):
            continue
        if isinstance(data, dict) and "claims" in data:
            content = data
            break
    add("申请文件 DOCX 与 PDF 已生成", bool(app and pdf), f"docx={app and app.name}, pdf={pdf and pdf.name}")

    report = run_checks(json.loads(json.dumps(content))) if content else None
    errors = [i for i in (report.items if report else []) if i["level"] == "ERROR"]
    add("检查脚本 0 个错误", report is not None and not errors,
        "; ".join(f"{i['code']} {i['where']}" for i in errors[:6]) or "0 errors")
    warn_codes = sorted({i["code"] for i in (report.items if report else []) if i["level"] == "WARN"})
    add("无范围类警告（C20–C25、D08、F10）", report is not None and not
        [c for c in warn_codes if c in {"C20", "C21", "C22", "C23", "C24", "C25", "D08", "F10"}],
        f"warnings: {warn_codes}")

    claims = "\n".join((content or {}).get("claims") or [])
    layout = all(k in claims for k in ("存储介质", "电子设备")) and bool(re.search(r"一种[^，,。]{0,40}(装置|系统)", claims))
    add("方法 + 装置/系统 + 电子设备 + 存储介质", layout, "")

    paras = docx_paragraphs(app) if app else []
    joined = "\n".join(paras)
    leaked = [k for k in ("来源论文", "材料缺口说明", "撰写说明", "待补充材料清单") if k in joined]
    add("申请文件不含非申请内容", app is not None and not leaked, f"found: {leaked}" if leaked else "clean")

    heads = [i for i, p in enumerate(paras) if re.fullmatch(r"(?:[一二三四五六七八九十]、)?说明书附图", p)]
    tail = [p for p in paras[heads[-1] + 1:] if p and p != "[IMG]"] if heads else ["(no 说明书附图)"]
    add("附图下只有“图N”", heads and all(re.fullmatch(r"图\s*\d+", p) for p in tail), f"{len(tail)} captions")

    notes_text = "\n".join(docx_paragraphs(notes_doc)) if notes_doc else ""
    add("撰写说明含集中交接清单", "待补充材料清单" in notes_text and "权属" in notes_text, notes_doc.name if notes_doc else "none")
    add("撰写说明含充分公开核查", "充分公开核查" in notes_text, "")

    workaround = [p.name for p in run.rglob("*.py") if re.search(r"draw|font|cjk|postprocess|render", p.name)]
    add("未编写绕过脚本", not workaround, f"{workaround}" if workaround else "none")

    out_nums = numbers(claims + json.dumps((content or {}).get("description", {}), ensure_ascii=False))
    small = {str(i) for i in range(0, 21)}
    unmatched = sorted(x for x in out_nums - numbers(source_text)
                       if x not in small and not re.fullmatch(r"[1-9]0\d|[1-9]\d{3}", x))
    add("数值都能在论文中找到", not unmatched, f"unmatched: {unmatched[:12]}")

    passed = sum(r["passed"] for r in results)
    grading = {"expectations": results,
               "summary": {"passed": passed, "failed": len(results) - passed, "total": len(results),
                           "pass_rate": round(passed / len(results), 3)}}
    (run / "grading.json").write_text(json.dumps(grading, ensure_ascii=False, indent=2), encoding="utf-8")
    return grading


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path)
    parser.add_argument("--source", type=Path, required=True, help="Paper text (pdftotext output) for the number audit.")
    args = parser.parse_args()
    source = args.source.read_text(encoding="utf-8", errors="ignore")
    for run in args.runs:
        g = grade(run, source)
        print(f"== {run}: {g['summary']['passed']}/{g['summary']['total']}")
        for r in g["expectations"]:
            print(f"   [{'PASS' if r['passed'] else 'FAIL'}] {r['text']} -- {r['evidence'][:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
