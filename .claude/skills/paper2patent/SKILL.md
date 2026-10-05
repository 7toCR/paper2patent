---
name: paper2patent
description: Turn an academic paper (PDF, LaTeX, pasted text, thesis chapter or technical disclosure) into a Chinese invention patent application draft — 说明书摘要、摘要附图、权利要求书、说明书、说明书附图 — delivered as DOCX/PDF with black-and-white patent drawings, plus a separate drafting-notes file covering novelty/disclosure risk, claim layout and claim-to-paper support. Use whenever the user wants to 论文转专利, 写专利/专利申请书/专利交底书, draft or review 权利要求书, write a 说明书, make 专利附图, or check a patent draft against its source paper, even if they only say "帮我把这篇论文写成专利".
---

# Paper2Patent

Convert a paper into a Chinese invention patent application draft that a patent attorney (专利代理师) can review and file with minimal rework. The output is a draft, not legal advice; say so once in the delivery message.

## What good looks like

A strong draft does four things the paper itself does not:

1. **Claims that define a protectable scope.** Claim 1 contains exactly the features needed to solve the technical problem (the distinguishing features over the closest prior art) and nothing paper-specific that a competitor could trivially design around. Specific values, model names and optional modules move to dependent claims and embodiments.
2. **A specification that enables and supports.** A skilled person can reproduce the invention from the 具体实施方式 alone, and every claim term is explained there. For AI inventions this means the model's modules/layers/connections, training steps and parameters, and how inputs and outputs map to the application scene (专利审查指南, 2026-01-01 revision).
3. **Technical character.** The solution is framed as technical means solving a technical problem with a technical effect, so it is not rejected as 智力活动的规则和方法 (专利法第25条).
4. **Complete fidelity.** Every technical feature is traceable to the paper. Patent-style generalisation is allowed where the paper supports it; invention is not. Missing information becomes an explicit `【待补充：…】` placeholder, never a guess — added matter cannot be supported later and misrepresents the inventors' work.

## Workflow

### 1. Intake

- Pick the mode: `direct` (default: draft everything, mark gaps), `human-in-loop` (confirm disclosure status, invention points and claim plan with the user before drafting), `text-only` (no files), `claims-only`, or `review` (check an existing draft against the paper).
- Read the **whole** paper: every section, equation, figure, caption, table and appendix. For a PDF, render the pages that contain the method figures and look at them; for text-only input, work from the figure descriptions and captions. The drawings must follow the paper's actual structure. See `references/input-requirements.md` for PDF handling and the minimum input.
- Establish the **disclosure status** (arXiv? accepted/published? public code? talk?) and dates. This decides whether the patent can still be novel. Read `references/patentability-and-disclosure.md` — every time, because the answer changes what you tell the user.

### 2. Source fact sheet (internal)

Before drafting, list the technical facts you will rely on, each with its location (§3.2, Eq. (4), Fig. 2, Table 3, Appendix B). Separate: (a) the paper's own contributions, (b) prior art the paper describes (related work, baselines), (c) experimental settings and results. This list is the backbone for fidelity, for `support_map`, and for the 背景技术 section. Do not show it to the user unless asked.

### 3. Invention mining and claim plan

Identify the closest prior art (usually the strongest baseline or the method the paper improves on), the distinguishing features, the technical problem they solve and the technical effect they produce. Then plan the claim tree before writing any claim: triage every candidate claim-1 feature (necessary / embodiment choice / interface detail), give each separable mechanism its own dependent claim (one fallback position per claim, never merged to save numbering), check that every branch of a generalised claim 1 is supported in the description, add the standard carrier claims, and record all of this in `notes.claim_plan`. Do not simply transcribe the paper's pipeline into claim 1. Read `references/claims-drafting.md`.

### 4. Draft the five parts

Follow `references/patent-drafting-standard.md` for the structure, content and language of each part, including the paper-to-patent mapping (what to keep, transform, or drop). Write in Simplified Chinese patent register: 本发明/本实施例, never 本文/我们/论文/作者. Keep technical clarifications (what a constraint or state actually means) in the text; move drafting remarks to the notes.

Then run the **sufficiency audit** (`patent-drafting-standard.md` §7): for every feature of claim 1 and the main dependent claims, check that the description states its data format, decision rule, failure handling and parameters. What the paper gives goes into the text; what it does not give goes into `notes.sufficiency` as a gap — never filled in by you. This audit is what produces a useful handover list; a draft that looks complete but hides its gaps is worse than one that names them.

### 5. Drawings

Design each figure as an explicit graph of nodes and edges taken from the paper's figures and method text. If the method checks, revises, retries or iterates, draw that loop (decision node + return edge) in the flowchart that illustrates claim 1, not just the success path. Read `references/drawing-generation.md`. A typical AI-method set: method flowchart (图1, also the 摘要附图), model/data-flow diagram redrawn from the paper's main figure, apparatus block diagram with reference numerals, electronic-device diagram.

### 6. Assemble, check, generate

Write the structured JSON described in `references/document-generation.md` (see `assets/example_patent_content.json` for a complete example). Then run, from the folder holding the JSON (`<skill>` = this skill's directory):

```bash
python <skill>/scripts/check_patent_draft.py patent.json
python <skill>/scripts/generate_patent_drawings.py patent.json -o out --update-json
python <skill>/scripts/generate_patent_docx.py patent.json -o out/<名称>_专利申请文件.docx --require-drawings
python <skill>/scripts/export_patent_pdf.py out/<名称>_专利申请文件.docx -o out/<名称>_专利申请文件.pdf --preview-dir out/preview
```

- Fix every `ERROR` from the checker and judge every `WARN`; rerun until clean. The checker catches the formal defects (single period, uncertain words, dependency rules, antecedent basis, 300-character abstract, figure numbering, reference numerals) that are easy to miss when re-reading your own text, and warns about scope problems (code field names or negative limitations in claims, an over-long or enumeration-heavy claim 1, a revision loop that no drawing shows, drafting remarks in the description).
- Look at every generated drawing PNG and at the preview pages before delivering. Fix the JSON and regenerate if anything is cramped, wrong or unsupported.
- The DOCX step also writes `<名称>_专利申请文件_撰写说明.docx`: it opens with the handover checklist (every `【待补充】`, `notes.handover`, plus ownership, disclosure date and prior-art search), followed by disclosure risk, claim plan, support map, drawing sources and check results. Keep all non-application content there, not in the application file.

Scripts need Python 3.9+. Pillow and a Chinese font are needed for drawings (the script refuses to render boxes-for-characters); LibreOffice for the PDF. If something is missing, install it or report the limitation — do not hand over drawings that show empty boxes.

### 7. Deliver

Give the user the files and a short message: the invention points claim 1 rests on, the claim structure (e.g. "方法1–6 + 装置7 + 设备8 + 介质9"), where the handover checklist is (first section of the 撰写说明) and its most important items, the disclosure/novelty assessment, and a reminder that a patent attorney should review the draft and run a prior-art search before filing. Do not paste the checklist or your analysis.

## Rules that matter most

- Fidelity beats completeness. No invented modules, parameters, datasets, hardware, scenarios, effects or numbers. Generalise only along lines the paper itself supports (alternatives it mentions, ablations, a generic description of a component).
- Claims are definite: no 等、约、可以、例如、优选、不限于 and the like; one final 句号 per claim; dependent claims cite only earlier claims; terms introduced before "所述" is used.
- Captions under drawings are just "图1", "图2"; titles go in 附图说明. No figure number, title, colour or shading inside an image.
- The application text contains the technical disclosure only. Keep evidence boundaries the paper states; move remarks about the drafting, the paper or missing files into `notes`, and requests for material into `notes.handover`.
- Be honest about what the draft is: it organises and discloses the paper's invention; it does not add inventive substance, and it says nothing about the chance of grant.
- Keep one invention name (≤25 characters, no brand or model names) consistent across the abstract, claims and 说明书.
- Never store the user's paper, drafts or personal data in repository files.

## Common requests

| Request | What to do |
|---|---|
| 把这篇论文写成专利 / 生成专利申请书 Word、PDF | Full workflow, `direct` mode |
| 先帮我梳理发明点再写 | `human-in-loop`: report disclosure status, invention points and claim plan; draft after confirmation |
| 只写权利要求书 | Steps 1–3, `claims-drafting.md`, run the checker on a JSON containing only claims |
| 根据说明书画专利附图 | `drawing-generation.md`; nodes and edges only from the text and paper figures |
| 检查这份专利草稿 / 是否忠实原文 | `review`: run the checker on the draft, then audit each claim feature against the paper using `quality-checklist.md` |
| 论文已经发表了还能申请吗 | Answer from `patentability-and-disclosure.md`; recommend confirming with a patent attorney |
