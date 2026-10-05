# Input Requirements

## Minimum input

Enough material to identify and enable the invention:

- the full paper (PDF, LaTeX source or text) — the method section, equations, figures with captions, experiment setup and results;
- or, failing that: title, abstract, the complete method description, the architecture/flow figure (image or detailed description) and the key results.

An abstract alone is not enough for a full draft. In `direct` mode draft what the material supports and mark the rest `【待补充：…】`; in `human-in-loop` mode ask for the missing parts first when they would change claim 1 or the embodiment.

## Information to obtain from the user (ask in `human-in-loop`; infer and flag in `direct`)

```text
【论文】PDF / arXiv 链接 / 正文
【公开情况】是否已上传 arXiv、录用或发表、公开代码或演讲？日期？
【未公开的补充】论文之外的实现细节、改进、实验（如有）
【申请人关注点】最想保护的部分、竞争对手可能的绕开方式（可选）
【输出】Word + PDF / 纯文本 / 仅权利要求书 / 附图 / 草稿审查
【模式】direct / human-in-loop
```

The disclosure question matters most; see `patentability-and-disclosure.md`.

## Reading a PDF

- Extract text with layout preserved (e.g. `pdftotext -layout paper.pdf paper.txt`, or the pdf skill if available). Check that equations and tables survived; re-read them from page images where extraction garbles them.
- Render the pages with the architecture and pipeline figures (e.g. `pdftoppm -r 110 -png -f 3 -l 4 paper.pdf fig`) and look at them. Note every box, arrow, branch and loop; this is the source for the drawings.
- Read the appendix: implementation details and hyperparameters often live there and are what makes the embodiment sufficient.
- Note the arXiv identifier, version, venue line and any "Published in"/DOI marks for the disclosure assessment.

If the PDF cannot be read, ask for the text of the abstract, method section and figure captions, plus images of the key figures.

## Input assessment (internal)

Before drafting, decide:

- **Completeness**: can a skilled person implement the method from this material? What is missing (layer sizes, loss weights, data preprocessing, prompt templates for LLM-based methods)?
- **Technical character**: what is the technical data and the technical effect? (`patentability-and-disclosure.md` §3)
- **Fidelity risk**: places where the paper is vague and drafting would require guessing. These become placeholders, not inventions.
- **Drawing readiness**: does the paper's figure or text define every node and connection you intend to draw?

## Handling gaps

`human-in-loop` gap request:

```text
当前材料不足以完成完整专利文本，请补充：
1. ……（例如：光照估计网络各卷积层的通道数）；
2. ……（例如：论文是否已在arXiv公开及日期）。
```

`direct` mode placeholder in the text, also listed in `gaps`:

```text
【待补充：多智能体之间传递的消息格式。】
```

Name what is missing; do not mention the paper inside the application text.

Placeholders mark missing source material only. They are never a licence to fill the gap with plausible modules, parameters, datasets, devices or scenarios.
