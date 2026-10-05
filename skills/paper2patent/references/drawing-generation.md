# Drawing Generation

Read when preparing 说明书附图 or reviewing drawings.

## Requirements (实施细则第21条, 审查指南第一部分第一章)

- Figures numbered 图1, 图2, … in the order the description introduces them. The figure number is printed **under** the figure ("图1"); figure titles do not appear on the drawing sheet — they belong in 附图说明.
- Black lines on white. No colour, grey fills, gradients, shadows, photos, 3-D effects, logos or watermarks.
- 附图中除必需的词语外，不应当含有其他注释. For flowcharts and block diagrams the words inside boxes are the necessary words; keep them short.
- Reference numerals used in a drawing must appear in the description text, and numerals mentioned in the text must appear in a drawing. The same component keeps the same numeral everywhere.
- Lines clear and even; the drawing stays legible when reduced to two-thirds; the abstract drawing stays legible at 4 cm × 6 cm.

## Which figures to make

Typical set for an AI/algorithm paper (adapt to the invention):

| Figure | Type | Content source |
|---|---|---|
| 图1 | `flowchart` | Steps of claim 1, S101…; usually the 摘要附图 |
| 图2 | `block` | Model / data-flow diagram redrawn from the paper's main architecture figure |
| 图3 | `flowchart` | Detail of a key sub-step or training procedure, if a dependent claim covers it |
| 图N-1 | `block` + `container` | Apparatus: modules 301, 302 … mirroring the apparatus claim |
| 图N | `block` | Electronic device: processor 401 ↔ memory 402 (generic carrier) |

Only draw what the claims and description need. Do not reproduce result plots, qualitative example images or photos — they are not line drawings and rarely support a claim.

## Draw the mechanism, not just the happy path

If the invention includes verification, revision, retry, iteration, convergence or fallback behaviour, the flowchart that illustrates claim 1 (usually 图1) must show it: a decision node (`shape: "decision"`) after the check, a "否" edge back to the step that is revised, and the "是" edge onward. A linear chain that only shows the success path makes the drawing describe a different, weaker method than the claims, and the examiner reads the figures together with the text.

Typical patterns:

- **Check after a stage**: `S103 构建场景记录 → S104 场景记录校验通过？ —否→ S103; —是→ S105`.
- **Bounded retries**: a second decision ("修订轮数是否用尽？") whose "是" edge leads to the stop/report step and whose "否" edge returns to the revision.
- **Checks acting on several stages**: one decision per stage, each looping back to its own stage; label an edge "上游修改后复核" when the paper re-checks dependent conditions after an upstream change. Put a very detailed version in its own figure if 图1 would become crowded, but keep at least the main loop in 图1.
- **One check, targeted return**: when a single check decides which stage failed, draw one labelled return edge per stage it can send work back to, rather than a single generic "否" edge, so the figure shows that only the failing stage is redone:

  ```json
  {"from": "S104", "to": "S101", "label": "需求未通过"},
  {"from": "S104", "to": "S102", "label": "场景未通过"},
  {"from": "S104", "to": "S103", "label": "音乐未通过"}
  ```

  Combine this with a stop condition (a second decision such as "输入缺失或轮次耗尽？") when the paper has one. Show both the targeted returns and the stop condition; reviewers found that drafts showing only one of the two were each missing part of the mechanism.

The checker warns (code F10) when the claims describe such a mechanism but no drawing has a decision node or loop.

## Figure spec format (JSON `drawings` entries)

```json
{
  "figure_no": 2,
  "title": "本发明实施例提供的……的结构示意图",
  "type": "block",
  "source": "论文图2；第3.2节",
  "container": {"ref": "300"},
  "nodes": [
    {"id": "enc", "label": "视觉编码器"},
    {"id": "dec", "label": "判断是否收敛", "shape": "decision"},
    {"id": "m1", "label": "特征提取模块", "ref": "301"}
  ],
  "edges": [
    {"from": "enc", "to": "m1"},
    {"from": "dec", "to": "enc", "label": "否"},
    {"from": "cpu", "to": "mem", "both": true}
  ]
}
```

- `type`: `flowchart` (wraps labels at ~18 characters) or `block` (~12 characters).
- `shape`: `process` (default rectangle), `decision` (diamond; label its outgoing edges 是/否), `terminal` (rounded; for 开始/结束 if wanted).
- `ref`: reference numeral, drawn outside the box with a leader line.
- `container`: draws a frame around all nodes, with an optional `ref` (e.g. the apparatus 300) and optional `label`.
- `edges`: `[from, to]`, `[from, to, label]` or objects; `both: true` for a double-headed arrow. Back edges (loops) are routed around the side automatically.
- `title` is for 附图说明 and the drafting notes only; it is never drawn.
- `source`: where in the paper the structure comes from (shown in the drafting notes).

## Fidelity rules for drawings

- **Nodes and edges come from the source.** Use the paper's figure (look at it), its caption and the method text; use the patent text only to normalise terms and numbering.
- **Never guess a connection.** If the paper does not say how two modules are connected, leave the edge out and add a `【待补充】` gap. The generator never adds edges on its own.
- Flowchart steps are sequential by definition; branches, loops and parallel paths must be stated in the paper (pseudo-code, "repeat until", "in parallel").
- Labels use the same terms as the claims; step labels start with the step number ("S102 生成场景描述文本"). Sub-steps of a step shown in a detail flowchart are numbered S1021, S1022, … (sub-steps of S102).
- Keep labels short: a step is a verb phrase (动作 + 对象 + 结果), not a sentence with reasons. The generator wraps long labels and never truncates them, so an overly long label produces a big box, not missing text.
- If the paper's figure contains elements outside the claimed invention (e.g. a baseline branch, a loss used only for an ablation), leave them out or mark them clearly in the description.

## Keeping figures legible

- Aim for at most ~15 nodes and at most 3 boxes side by side per figure. A paper's overview figure often needs two patent figures (e.g. scene understanding / music planning). The generator warns when a figure has many nodes or when the text would print smaller than ≈2.2 mm.
- Use `type: "block"` (narrower boxes) for rows of several modules; `flowchart` boxes are wider and suit a single column of steps.
- The order of `nodes` is the initial left-to-right order within each row. If a loop arrow is reported to cross boxes, move its endpoints to the start or end of the list so they sit at the edge of their rows.

## Generation and review

```bash
python <skill>/scripts/generate_patent_drawings.py patent.json -o out --update-json
```

Writes `<prefix>_图N.svg` and `<prefix>_图N.png` (300 dpi, grayscale, real Chinese font) and fills `drawing_assets` and `image_model_prompts` in the JSON. It fails loudly on unknown node IDs, empty labels, figure numbers inside labels, or when no Chinese font is available (set `PATENT_CJK_FONT=/path/to/font` if needed).

Then **open each PNG and look at it**: correct structure, readable text, no overlapping lines or labels, arrows pointing the right way. If something looks wrong, change the spec (shorter labels, a different node order in `nodes`, splitting a crowded figure into two) and regenerate.

Legacy string specs ("图1：……包含步骤S101，……；S102，……") still work for simple step lists; module lists given as strings are drawn without edges and produce a warning. Rewrite them in the structured form.

## Optional: image-model refinement

`image_model_prompts` contains one prompt per figure for a two-stage flow (generated PNG as structural reference → image model such as Gemini for a cleaner rendering). The generated SVG/PNG is already filing-grade line art, so refinement is optional. If used, compare the refined image with the reference node by node and edge by edge; reject any image that adds, drops or renames anything, adds a title, or uses grey or colour. An image model is never a source of technical content.
