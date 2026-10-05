#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export the application DOCX to PDF and optionally render preview pages.

LibreOffice (soffice) is used when available, with a throw-away user profile
so a running LibreOffice instance or a locked profile does not break the
conversion. Without LibreOffice, `--content-json` renders an image-based
review PDF directly from the patent JSON (clearly a fallback: not editable,
not for filing).

`--preview-dir DIR` writes one PNG per PDF page (needs `pdftoppm` from
Poppler, or PyMuPDF) so the drafter can look at the result before delivery.

Usage:
    python export_patent_pdf.py out/申请文件.docx --output out/申请文件.pdf --preview-dir out/preview
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patent_common import (  # noqa: E402
    DESCRIPTION_SECTIONS,
    abstract_figure_no,
    as_paragraphs,
    claims_list,
    load_cjk_font,
    read_json,
    resolve_path,
)


def find_soffice(explicit: str | None = None) -> str | None:
    candidates = [c for c in (explicit, os.environ.get("SOFFICE")) if c]
    candidates += [
        "soffice",
        "libreoffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def export_with_soffice(docx: Path, output: Path, soffice: str, timeout: int = 180) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p2p_lo_") as profile, tempfile.TemporaryDirectory(prefix="p2p_out_") as outdir:
        cmd = [
            soffice,
            f"-env:UserInstallation={Path(profile).resolve().as_uri()}",
            "--headless", "--norestore",
            "--convert-to", "pdf",
            "--outdir", outdir,
            str(docx.resolve()),
        ]
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        produced = Path(outdir) / f"{docx.stem}.pdf"
        if result.returncode != 0 or not produced.exists():
            message = (result.stderr or result.stdout or "LibreOffice conversion failed.").strip()
            raise RuntimeError(message)
        shutil.move(str(produced), str(output))
    if output.stat().st_size == 0:
        raise RuntimeError("PDF conversion produced an empty file.")


# ---------------------------------------------------------------------------
# Image-based fallback renderer (review copy only)
# ---------------------------------------------------------------------------

class PageCanvas:
    W, H = 1240, 1754  # A4 at 150 dpi
    MX, MT, MB = 125, 115, 120

    def __init__(self) -> None:
        from PIL import Image, ImageDraw

        self.Image, self.ImageDraw = Image, ImageDraw
        self.body = load_cjk_font(24)
        self.small = load_cjk_font(20)
        self.title = load_cjk_font(32)
        self.pages: list[Any] = []
        self.new_page()

    def new_page(self) -> None:
        self.page = self.Image.new("L", (self.W, self.H), 255)
        self.draw = self.ImageDraw.Draw(self.page)
        self.pages.append(self.page)
        self.y = self.MT

    def ensure(self, needed: int) -> None:
        if self.y + needed > self.H - self.MB:
            self.new_page()

    def wrap(self, text: str, font: Any, width: int, indent: int) -> list[str]:
        lines, current, limit = [], "", width - indent
        for ch in text:
            if current and self.draw.textlength(current + ch, font=font) > limit:
                lines.append(current)
                current, limit = ch, width
            else:
                current += ch
        return lines + ([current] if current else [])

    def heading(self, text: str, new_page: bool) -> None:
        if new_page:
            self.new_page()
        w = self.draw.textlength(text, font=self.title)
        self.draw.text(((self.W - w) / 2, self.y), text, fill=0, font=self.title)
        self.y += 70

    def centered(self, text: str, font: Any) -> None:
        self.ensure(50)
        w = self.draw.textlength(text, font=font)
        self.draw.text(((self.W - w) / 2, self.y), text, fill=0, font=font)
        self.y += 50

    def paragraph(self, text: str, indent: bool = True, bold: bool = False) -> None:
        width = self.W - 2 * self.MX
        ind = 48 if indent else 0
        for i, line in enumerate(self.wrap(text, self.body, width, ind)):
            self.ensure(40)
            self.draw.text((self.MX + (ind if i == 0 else 0), self.y), line, fill=0, font=self.body)
            if bold:
                self.draw.text((self.MX + 1 + (ind if i == 0 else 0), self.y), line, fill=0, font=self.body)
            self.y += 40
        self.y += 6

    def image(self, path: Path, label: str | None) -> None:
        img = self.Image.open(path).convert("L")
        max_w, max_h = self.W - 2 * self.MX, self.H - self.MT - self.MB - 80
        scale = min(max_w / img.width, max_h / img.height, 1.0)
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
        self.ensure(img.height + 70)
        self.page.paste(img, ((self.W - img.width) // 2, self.y))
        self.y += img.height + 16
        if label:
            self.centered(label, self.body)

    def save(self, output: Path) -> None:
        for i, page in enumerate(self.pages, start=1):
            draw = self.ImageDraw.Draw(page)
            label = str(i)
            w = draw.textlength(label, font=self.small)
            draw.text(((self.W - w) / 2, self.H - 70), label, fill=0, font=self.small)
        first, *rest = [p.convert("RGB") for p in self.pages]
        first.save(output, "PDF", save_all=True, append_images=rest, resolution=150)


def render_from_json(content_json: Path, output: Path) -> None:
    data = read_json(content_json)
    base = content_json.parent
    assets = [a for a in data.get("drawing_assets") or [] if isinstance(a, dict) and a.get("png_path")]
    figures = sorted(((int(a.get("figure_no") or 0), resolve_path(a["png_path"], base)) for a in assets))
    c = PageCanvas()
    c.heading("说明书摘要", new_page=False)
    for text in as_paragraphs(data.get("abstract")):
        c.paragraph(text)
    c.heading("摘要附图", new_page=True)
    fig_no = abstract_figure_no(data)
    chosen = next((p for n, p in figures if n == fig_no), figures[0][1] if figures else None)
    if chosen:
        c.image(chosen, None)
    c.heading("权利要求书", new_page=True)
    for claim in claims_list(data):
        c.paragraph(claim)
    c.heading("说明书", new_page=True)
    c.centered(str(data.get("invention_name") or ""), c.body)
    desc = data.get("description") if isinstance(data.get("description"), dict) else {}
    for key, heading in DESCRIPTION_SECTIONS:
        c.paragraph(heading, indent=False, bold=True)
        for text in as_paragraphs(desc.get(key)):
            c.paragraph(text)
    c.heading("说明书附图", new_page=True)
    for n, path in figures:
        c.image(path, f"图{n}")
    output.parent.mkdir(parents=True, exist_ok=True)
    c.save(output)


def render_previews(pdf: Path, out_dir: Path, dpi: int = 60) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", str(pdf), str(prefix)], check=True, timeout=180)
        return sorted(out_dir.glob("page-*.png"))
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError:
        print("Preview skipped: install Poppler (pdftoppm) or PyMuPDF to render page images.", file=sys.stderr)
        return []
    doc = fitz.open(str(pdf))
    paths = []
    for i, page in enumerate(doc, start=1):
        path = out_dir / f"page-{i:02d}.png"
        page.get_pixmap(dpi=dpi).save(str(path))
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the patent DOCX to PDF.")
    parser.add_argument("docx", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--soffice", help="Explicit path to soffice/libreoffice.")
    parser.add_argument("--content-json", type=Path, help="Patent JSON for the image-based fallback when LibreOffice is missing.")
    parser.add_argument("--preview-dir", type=Path, help="Render PNG previews of every PDF page into this folder.")
    args = parser.parse_args()
    if not args.docx.exists():
        print(f"ERROR: {args.docx} not found", file=sys.stderr)
        return 2
    soffice = find_soffice(args.soffice)
    fallback = False
    if soffice:
        try:
            export_with_soffice(args.docx, args.output, soffice)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print(f"LibreOffice failed: {exc}", file=sys.stderr)
            soffice = None
    if not soffice:
        if not args.content_json:
            print("LibreOffice not available. Keep the DOCX as the deliverable, or pass --content-json "
                  "for an image-based review PDF.", file=sys.stderr)
            return 3
        render_from_json(args.content_json, args.output)
        fallback = True
    print(f"Wrote {args.output} ({args.output.stat().st_size} bytes{', image-based fallback' if fallback else ''})")
    if args.preview_dir:
        pages = render_previews(args.output, args.preview_dir)
        if pages:
            print(f"Previews: {len(pages)} pages in {args.preview_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
