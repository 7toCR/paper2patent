# Patent Drafting Standard (five parts)

The normative standard for the content of a Chinese invention application drafted from a paper. Claims have their own file: `claims-drafting.md`.

Legal anchors: 专利法第26条 (说明书清楚完整、权利要求以说明书为依据、摘要简要说明技术要点)；实施细则第20–26条；专利审查指南第一部分第一章、第二部分第二章.

## Contents

1. Language rules for the whole application
2. 发明名称
3. 说明书摘要 and 摘要附图
4. 说明书: 技术领域 / 背景技术 / 发明内容 / 附图说明 / 具体实施方式
5. Paper → patent mapping
6. Before/after examples
7. Sufficiency audit

## 1. Language rules

- Simplified Chinese, technical register. Refer to the invention as 本发明 / 本申请 / 本实施例. Never 本文、本论文、我们、作者、实验室、本工作.
- One term per concept across abstract, claims, description and drawings. If the paper alternates between "encoder" and "feature extractor", pick one Chinese term and use it everywhere.
- First use of an abbreviation: Chinese name + English full name + abbreviation, e.g. 大语言模型（Large Language Model，LLM）; afterwards the Chinese term or the abbreviation.
- Formulas are allowed; define every symbol right after the formula ("其中，x表示……"). Number formulas in the description as （1）、（2）.
- No commercial or self-praising language (最先进、领先、革命性、完美、SOTA) anywhere; 实施细则第20条 and 第26条 forbid it in the description and abstract.
- The description must not use "如权利要求……所述" references (实施细则第20条).
- Effects are argued, not asserted: tie each effect to the feature that causes it, and support it with the paper's own measurements where available.
- **Three kinds of explanatory sentences — keep two, move one.**

  | Kind | Example | Where it goes |
  |---|---|---|
  | Technical clarification: what a parameter, state or step actually means | "50至500个字符的约束针对任务指令的长度，而非音乐或歌词长度"；"字段非空不表示存在对应证据，缺少证据时填入显式缺失标记"；"修正回路仅返回未通过检查的阶段，并不重新执行全部模态处理" | Keep in the description, next to the feature it clarifies. These improve clarity and sufficiency. |
  | Evidence boundary the paper states | "上述组件实验同时移除了检查、语义细化、格式规范化和重试，其效果归因于该组合"；"未评估节拍级同步" | Keep once, briefly, at the effect it bounds. |
  | Drafting-process remark | "本文未补入论文未披露的超时重试策略"；"不表示本初稿编制过程已运行这些服务"；"论文未说明……"；notes on missing files | Move to `notes` (the 撰写说明). The checker flags these (D08). |

  Being careful about evidence is right; narrating that care inside the application text is not.
- **Keep the paper's modality.** "提示要求所有必要检查通过后才接受" is not "系统保证不合格结果不会被合成". Write effects and mechanisms at the strength the paper supports; absolute words (保证、杜绝、彻底、一切、完全避免) need direct evidence (checker C25).
- **Placeholders are short and local.** Inside the application text a `【待补充：…】` placeholder only names what must be inserted at that point. Why it is needed and what the inventor should provide belong in the handover list (`notes.handover`, see `document-generation.md`).

## 2. 发明名称

- Normally ≤25 characters (审查指南; up to 40 only in special cases such as chemistry). No person names, place names, trademarks, model numbers, product names (GPT-4o, ResNet-50) or advertising words.
- Reflect the subject and the claim categories: "视频配乐生成方法、装置、电子设备及存储介质", "基于多智能体的视频配乐生成方法及系统".
- The 说明书 starts with the name; the abstract opens with it; claim 1's subject matches its first category.

## 3. 说明书摘要 and 摘要附图

- ≤300 characters **including punctuation** (审查指南). One paragraph.
- Content: name and technical field; the technical problem (briefly); the key points of the solution (the steps of claim 1, condensed); the main use. Effects in one clause at most.
- Template: "本发明公开了一种……，涉及……技术领域。该方法包括：……；……；……。本发明能够……，可用于……。"
- Reference numerals, if any, in parentheses. No keyword list, no "参见附图X", no promotional wording.
- 摘要附图: the one figure that best shows the technical features, normally the method flowchart (图1). Set `abstract_figure` in the JSON; in the document it appears without a caption. It must stay legible when reduced to 4 cm × 6 cm, so prefer a figure with few, short labels.

## 4. 说明书

### 技术领域

One or two sentences: "本发明涉及……技术领域，具体涉及一种……". The field is the technical field of application (图像处理、语音信号处理、自然语言处理、机器人控制), consistent with the abstract.

### 背景技术

Purpose: let the examiner understand the invention and see the problem. Typical length 500–1500 characters, three layers:

1. Technical context: what the task is and the basic concepts needed (definitions), only as much as a skilled reader needs.
2. Existing technology: the mainstream approaches, and — where the paper provides them — 1 to 3 closest prior-art documents cited from the paper's references (title, venue, year as the paper cites them). Describe what each does, objectively.
3. Existing problems: only problems the paper itself identifies; for each, the cause (why it happens) and the consequence (what goes wrong). The last paragraph should lead naturally to the problem the invention solves.

Do not disparage, do not quote the paper's novelty claims, do not describe the invention here.

### 发明内容

Three parts, in this order:

1. 要解决的技术问题: "本发明的目的在于提供一种……，以解决现有技术中……的问题。" — mirrors the problems in 背景技术.
2. 技术方案: "为实现上述目的，本发明提供如下技术方案：" followed by the full text of claim 1 (converted to description wording); then one "进一步地，……" paragraph per dependent claim; then the apparatus, electronic device and storage medium in one or two sentences. The description must literally support every claim feature (专利法第26条第4款), so do not paraphrase claim features into something narrower or different.
3. 有益效果: "与现有技术相比，本发明的有益效果在于：" — one point per distinguishing feature, each stated as cause → effect ("由于……，因此……"), with the paper's quantitative results where they exist (dataset, metric, value, compared method). Never add numbers the paper does not report.

### 附图说明

Opening sentence ("为了更清楚地说明本发明实施例的技术方案，下面将对实施例描述中所需要使用的附图作简单介绍。"), then one line per figure in order: "图1为本发明实施例提供的……方法的流程示意图；" … ending with "。". These lines are where figure titles live.

### 具体实施方式

The section that decides sufficiency and support. For an AI paper it is usually the longest part (often 3000–8000 characters). Structure:

1. Opening boilerplate ("下面将结合本发明实施例中的附图，对本发明实施例中的技术方案进行清楚、完整地描述……").
2. **实施例一 (method)**, following 图1 step by step (S101, S102, …). For every step answer four questions in patent language: what the step is; what problem it addresses; how it works (inputs, outputs, intermediate results, formulas with symbols defined, the model's modules/layers/connections, parameter values from the paper); what it achieves. Refer to the figures ("结合图2，……").
3. Training (when the invention involves a model): training data (what kind, how paired or labelled, the datasets the paper uses), loss function(s) with formulas, optimiser and hyperparameters as reported, number of iterations, stopping criteria. Inference procedure if it differs from training.
4. A concrete example drawn from the paper's experiments (dataset, settings) and an effect-verification paragraph with the paper's results; tables are fine (`{"table": [[…]], "caption": "表1 ……"}`). Use the paper's implementation section fully (models and versions used for each component, checkpoints, seeds, evaluation protocol, how metrics are computed); this is disclosed material and strengthens sufficiency.
5. **A worked instance of the core mechanism**, when the paper provides one (case study, qualitative example, appendix sample, prompt/response listing): follow one input through the intermediate artefacts (e.g. scene records → blueprint → conflicting proposals → revision → generator record) to the output. Model names and result tables do not replace this. If the paper contains no such instance, do not construct one: add a handover item asking the inventors for a real run record, or for an illustrative example they confirm and that is labelled as illustrative.
6. **Alternative embodiments** only where the paper supports them: variants mentioned in the text, ablation configurations, alternative backbones or parameter ranges the paper evaluates. If claim 1 uses a generic term (e.g. "预训练语言模型"), give the concrete instance(s) the paper uses. Do not create alternatives the paper never mentions.
7. **Apparatus embodiment** (图 with modules 301, 302, …): one sentence per module mirroring the method steps, then "各模块的具体实现方式与实施例一中的对应步骤相同".
8. **Electronic device and storage medium embodiment** (processor 401, memory 402, …): generic carrier wording. Hardware the paper reports (e.g. the GPU used in experiments) may be named as an example.
9. Closing boilerplate (protection scope sentence).

Every reference numeral used in a drawing must appear in this text, and vice versa (实施细则第21条).

## 5. Paper → patent mapping

| Paper part | Goes to | Treatment |
|---|---|---|
| Title, abstract | 发明名称, 技术领域, 摘要 | Rewrite as a technical subject; drop marketing |
| Introduction (motivation) | 背景技术 problems, 发明内容 purpose | Keep only technical problems, with cause and consequence |
| Related work | 背景技术 existing technology | Cite 1–3 closest documents the paper cites; describe objectively |
| Method / approach | Claims, 发明内容, 具体实施方式 | Turn into steps (method) and modules (apparatus); keep all implementation detail in the embodiment |
| Equations | 具体实施方式; claims only when the formula is the inventive point | Define every symbol; keep the paper's notation consistent |
| Architecture figure | 说明书附图 | Redraw as nodes and edges; keep the paper's structure |
| Algorithm pseudo-code | Method steps, possibly a flowchart with decision/loop | Loops and conditions become decision nodes and back edges |
| Experiments: setup | 具体实施方式 example | Datasets, hyperparameters, hardware as reported |
| Experiments: results | 有益效果, effect verification | Only reported numbers; name the compared method and metric |
| Ablations | Dependent claims, alternative embodiments | Each ablated component that matters is a fallback position |
| Theory, proofs | Usually dropped | At most one sentence of technical rationale |
| Limitations, future work | Dropped | Never present future work as an embodiment |
| Authors, affiliations, acknowledgements, funding | Never | — |

## 6. Before/after examples

Paper: "We propose a novel multi-scale attention module that significantly outperforms SOTA methods."
Patent (有益效果): "多尺度注意力去噪网络通过不同尺度的卷积提取反射分量中不同空间范围的噪声特征，并由通道注意力权重自适应地确定各尺度特征的贡献，从而在抑制暗区噪声的同时保留亮区细节；在LOL测试集上，峰值信噪比由16.8dB提升至23.1dB。"

Paper: "Our agents collaborate to plan the music."
Patent (step): "S103，音乐规划智能体根据场景描述文本，为每个镜头生成包含节奏、调式和配器信息的分段音乐提示词。" — only if the paper says the prompt contains those three items; otherwise "生成分段音乐提示词" plus a `【待补充：分段音乐提示词包含的具体信息。】` placeholder if the detail is needed for sufficiency.

## 7. Sufficiency audit

Run this after drafting and before generating files. It is what turns "the draft looks complete" into "we know what is still missing".

For claim 1 and each main dependent claim, take every technical feature and ask four questions:

1. **Data**: what exactly goes in and comes out (structure, fields, format, example values)?
2. **Rule**: how is the decision or transformation made (criterion, threshold, prompt or model, comparison performed)?
3. **Failure**: what happens when it fails (what is reported, how the failing stage is located, what is redone, what is re-checked downstream, when it stops)?
4. **Parameters**: which settings are needed to reproduce it?

For each answer: if the paper gives it, make sure the description states it (cite the paragraph); if the paper does not, do not fill it in — record it as a gap. Write the result to `notes.sufficiency`:

```json
[{"claim": 2, "feature": "语义一致性检查", "status": "gap",
  "where": "说明书S104段", "missing": "不一致的判定准则、检查结果的输出格式、如何定位未通过的阶段"},
 {"claim": 1, "feature": "场景记录的时间排序", "status": "disclosed", "where": "说明书S102段；论文§2.1"}]
```

Every `gap` item flows automatically into the handover checklist at the top of the 撰写说明. Also set `notes.worked_example` to the paper location of a complete worked instance of the core mechanism if one exists (case study, appendix sample); if it is absent, the checklist asks the inventors for a real run record (input → intermediate artefacts → output).

Typical gaps in LLM/agent papers: prompt templates; the format of structured messages between components; judgement criteria of LLM-based checks; how failures are attributed to a stage; backend label vocabularies; configuration of optional branches the claims cover (e.g. the no-video path).
