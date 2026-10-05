# Document Generation

The JSON contract consumed by the scripts, the generation pipeline and the delivery checks. A complete, check-clean example lives in `assets/example_patent_content.json`; copy its structure.

## JSON contract

```json
{
  "invention_name": "……方法、装置、电子设备及存储介质",
  "source_title": "Paper title (drafting notes only)",
  "abstract": "≤300 characters incl. punctuation, one paragraph",
  "abstract_figure": 1,
  "claims": ["1.一种……，其特征在于，……。", "2.根据权利要求1所述的……，其特征在于，……。"],
  "description": {
    "technical_field": "本发明涉及……",
    "background": ["paragraph", "paragraph"],
    "invention_content": ["本发明的目的在于……", "为实现上述目的……", "进一步地，……", "与现有技术相比，……"],
    "drawing_description": ["为了更清楚地说明……", "图1为……；", "图2为……。"],
    "embodiments": [
      "paragraph",
      {"formula": "R(x) = I(x) / max(L(x), ε)", "label": "（1）"},
      {"table": [["方法", "指标"], ["本实施例", "23.1"]], "caption": "表1 ……"}
    ]
  },
  "drawings": [{"figure_no": 1, "title": "……的流程示意图", "type": "flowchart", "nodes": [], "edges": [], "source": "论文图2"}],
  "support_map": {"1": ["§3.1", "Eq. (2)", "Fig. 2"], "2": ["§3.2"]},
  "gaps": ["【待补充：……。】（where it appears）"],
  "notes": {
    "source": "title, authors, venue, arXiv version",
    "disclosure_status": "…",
    "risks": ["…"],
    "patentability": "…",
    "invention_points": ["区别特征：…", "技术问题：…", "技术效果：…"],
    "prior_art": "…",
    "claim_plan": ["权利要求1特征A：必要（区别特征，解决……）", "特征B：实施例选择 → 从属权利要求3", "…"],
    "sufficiency": [
      {"claim": 1, "feature": "……", "status": "disclosed", "where": "说明书S102段；论文§2.1"},
      {"claim": 2, "feature": "……检查", "status": "gap", "where": "说明书S104段", "missing": "判定准则；检查结果格式；失败阶段如何定位"}
    ],
    "worked_example": "论文附录B的完整示例（若论文没有，留空，清单会请发明人提供）",
    "handover": [
      {"category": "技术细节", "item": "各智能体所用提示词模板", "why": "充分公开"},
      {"category": "工程资料", "item": "一次真实运行的中间产物记录（输入→中间结果→输出）", "why": "具体实施方式中的完整实例"}
    ],
    "next_steps": ["…"]
  }
}
```

Field notes:

- Each description section is a string or a list. List items are paragraphs, `{"formula", "label"}` objects (centred formula line, number at the right margin; write subscripts and superscripts as `x_i`, `x_{pkg}`, `L(x)^γ`, `A^(h)` and they are typeset) or `{"table", "caption"}` objects (first row is the header; keep tables to ≤7 columns — split wider result tables — because columns are sized to their content on an A4 page).
- `claims`: one string per claim, already numbered.
- `drawings`: see `drawing-generation.md`. `drawing_assets` and `image_model_prompts` are written by the drawing script; do not write them by hand.
- `notes.sufficiency` is the result of the sufficiency audit (`patent-drafting-standard.md` §7); it is rendered as a table in the 撰写说明 and every `gap` row is added to the handover checklist. `notes.worked_example` names where the paper gives a complete worked instance; when it is empty the checklist asks the inventors for one.
- `notes.handover` is the central handover checklist (category, what to provide, why). The 撰写说明 file opens with it, merges in every `gaps` entry, and always adds the standard items (applicant/inventors and ownership, first-disclosure date and scope, prior-art search). Put requests for material that is not needed at a specific spot in the text here, rather than as inline placeholders.
- `support_map`, `gaps` and `notes` never appear in the application file; they go into the 撰写说明 document. In `support_map`, prefix the paper's own locations with 论文 ("论文§3.1", "论文图2", "论文表1") so they are not confused with the patent's 图/表 numbers.
- Every `【待补充：…】` placeholder in the text must also be listed in `gaps`. Word placeholders as the missing content itself ("【待补充：光照估计网络各卷积层的通道数。】"), not as "论文未给出……": the application text must not refer to the paper.
- Legacy fields still accepted: `abstract_drawing` (text containing 图N) instead of `abstract_figure`; string entries in `drawings`.

Write the JSON with UTF-8 and real Chinese punctuation. Prefer writing it with a file tool rather than shell heredocs, so quotes inside formulas do not break.

## Pipeline

Run from the folder that holds the JSON; `<skill>` is this skill's directory.

```bash
# 1. Formal checks (repeat until no ERROR; judge each WARN)
python <skill>/scripts/check_patent_draft.py patent.json

# 2. Drawings: SVG + PNG, updates drawing_assets in the JSON
python <skill>/scripts/generate_patent_drawings.py patent.json -o out --update-json

# 3. Application DOCX + drafting notes DOCX (<name>_撰写说明.docx)
python <skill>/scripts/generate_patent_docx.py patent.json -o out/<名称>_专利申请文件.docx --require-drawings

# 4. PDF via LibreOffice + page previews
python <skill>/scripts/export_patent_pdf.py out/<名称>_专利申请文件.docx -o out/<名称>_专利申请文件.pdf --preview-dir out/preview
```

Options:

- `generate_patent_docx.py --number-paragraphs` prefixes description paragraphs with [0001]-style numbers (useful for review; CNIPA's filing client can also add them).
- `--embed-svg` additionally embeds the SVG (Word 2016+ then shows vector graphics; the PNG remains the fallback).
- `--notes-output PATH` / `--no-notes` control the drafting-notes file.
- `export_patent_pdf.py --content-json patent.json` renders an image-based review PDF when LibreOffice is not installed. Tell the user it is a review copy, not an editable or fileable document.

What the application DOCX contains: 说明书摘要 → 摘要附图 (image only) → 权利要求书 → 说明书 (name, then 技术领域, 背景技术, 发明内容, 附图说明, 具体实施方式) → 说明书附图 (each image with "图N" underneath). Each part starts on a new page; pages are numbered; A4, 宋体 小四, 1.5 line spacing.

## Delivery checks

Before telling the user the files are ready:

1. The checker reports 0 errors, and the remaining warnings are deliberate.
2. You have looked at every drawing PNG and at the preview pages: part order, page breaks, figures not clipped, tables intact, no placeholder you did not intend.
3. Every `【待补充】` is listed in `gaps` and mentioned in your message.
4. The 撰写说明 file exists and its disclosure/risk section reflects what you found.
5. File names do not leak private paths; generated files are not committed to any repository unless the user asks.

If LibreOffice, Pillow or a Chinese font is unavailable and cannot be installed, deliver what works (the DOCX needs PNG drawings, so drawings come first) and state the limitation precisely.
