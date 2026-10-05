# Claims Drafting

Read before writing or revising claims. The claims decide what the patent protects; everything else in the application exists to support them.

Legal anchors: 专利法第26条第4款 (以说明书为依据，清楚、简要)；实施细则第22–25条；专利审查指南第二部分第二章第3节.

## 1. Plan the claim tree first

Write the plan into `notes.claim_plan` (it goes to the drafting notes):

1. **Closest prior art**: the baseline or earlier method the paper improves on most directly.
2. **Distinguishing features**: what the paper does that this prior art does not. These are the candidates for claim 1's characterising part.
3. **Technical problem and effect** of those features (from the paper's analysis and experiments).
4. **Claim 1 scope**: all features *necessary* to solve that problem (必要技术特征), and no more. Every extra feature in claim 1 is an extra element an infringer must copy; every missing necessary feature makes the claim unsupported or not inventive.
5. **Fallback positions**, ranked by value: features that would rescue patentability if claim 1 falls — ablation-proven components, key structural details, specific formulas, key parameter choices, training strategy.
6. **Carrier claims** for computer-implemented inventions: apparatus, electronic device, storage medium.

### Feature triage for claim 1

A paper describes a whole system; claim 1 should not simply transcribe its pipeline. Before writing claim 1, list every candidate feature and sort it into one of three bins. Record the result in `notes.claim_plan`, so the attorney can see why each claim-1 feature is there.

| Bin | Test | Where it goes |
|---|---|---|
| A. Necessary | Without it the stated technical problem is not solved, or it is what distinguishes the method from the closest prior art | Claim 1 |
| B. Embodiment choice | The paper uses it, but the mechanism would still work with a different choice: the number or split of agents/modules, complete enumerations ("角色、能力、约束、工作流程和可用工具"), thresholds and round limits, specific field lists, model names | Dependent claim (if worth a fallback) or embodiment only |
| C. Interface detail | Code field names, variable names, file formats, prompt wording, what an interface happens to lack | Embodiment only |

Rules of thumb that follow from the triage:

- **Claim functions, not organisation.** "根据场景记录中的主体情绪生成描述标签提议" is the technical feature; "由作曲智能体生成" is how the embodiment organises it. Put the role split in a dependent claim unless the paper shows that the separation itself produces the effect.
- **Enumerations.** In claim 1, keep the generic definition ("所述智能体档案限定所述智能体的处理范围和约束条件") and move the paper's full list to a dependent claim, unless every member is necessary. Lists of *alternatives* ("视频、音频、图像和文本中的至少一种") broaden the claim and are fine.
- **No negative limitations by default.** "所述生成器记录不包括速度字段" narrows the claim and is rarely a technical contribution. State what an implementation lacks in the embodiment; claim an absence only when the paper presents the absence as the solution.
- **No code identifiers.** Write the technical meaning ("歌词及结构文本") in the claims; field names such as `gt_lyric` go into the embodiment. Mathematical variables in a formula are fine.
- **Length check.** A claim 1 beyond roughly 500–600 characters usually contains bin-B material. Re-triage before accepting it.

Narrower is not automatically safer and broader is not automatically better: remove a feature from claim 1 only when the description still supports the broader claim and the remaining features still solve the problem.

### Supporting a broader claim 1

When claim 1 generalises (a list of alternatives such as "视频、源音频或有序背景文本", or a generic term replacing the paper's component), every branch it covers must be described in the description to the extent the paper describes it. For each generalisation, record in `notes.claim_plan` which passages implement each branch. If the paper mentions a branch only in passing (one sentence, no procedure), either keep it with a risk note ("分支X的实施细节较少，需发明人补充或在审查中可能被要求缩小") and a handover item, or narrow claim 1. A broader claim is also only meaningful after a prior-art search; say so in `notes.risks`.

### Generalisation ladder

Claim 1 may describe a paper-specific element more generally only when the paper supports the generalisation:

- the paper names alternatives or says the component is replaceable → generic term in claim 1, specific one in a dependent claim and the embodiment;
- the paper's function is described in functional terms → functional wording is acceptable;
- the paper only ever uses one specific model or value and gives no reason it matters → keep it out of claim 1 if it is not essential to the inventive effect; put it in a dependent claim/embodiment.

Model names (GPT-4o, CLIP, ResNet-50), dataset names and hyperparameter values almost never belong in claim 1.

### Dependent claims: one mechanism each

Each dependent claim is a fallback position: if the claims above it fall, it must stand on its own technical contribution. So:

- **One technical mechanism per dependent claim.** If the paper has several separable mechanisms (for example: the structure of a scene record; how image context is merged into records; how audio events are anchored to visual anchors; a backward global refinement pass), give each its own claim. Do not merge independent mechanisms into one claim to save numbering: a merged claim can only be used, amended or argued as a whole.
- **Order by value**: mechanisms backed by the paper's ablations or analysis first, then structural details, then parameters.
- **Sub-mechanisms chain**: a refinement of a mechanism depends on that mechanism's claim ("根据权利要求3所述……，其特征在于，……"), so the tree mirrors the technical structure.
- **Budget**: if there are more valuable mechanisms than slots under the 10-claim fee threshold, prefer separate claims and tell the user that claims beyond 10 cost an extra fee, or list the remaining ones in `notes.claim_plan` as "备选从属权利要求" for the attorney to choose. Never merge to fit the budget.

### Configurable parameters

Values the paper reports (length limits such as 50–500 characters, "at least three constraints", round budgets of 3/2/2, thresholds, layer counts) are faithful material but rarely inventive by themselves. Put a parameter in a dependent claim only when the paper shows it matters (ablation, sensitivity analysis, or a stated reason why that value is needed); otherwise keep it in the embodiment as a configuration of the example.

### Claim the strength the paper supports

Keep the paper's modality. "The verification prompt requires all checks to pass before acceptance" supports "在通过所述检查之前不接受……的输出"; it does not support "确保/保证不合格结果不会被合成" or "可靠地阻止一切错误". Words such as 保证、确保一切、必然、彻底、杜绝、完全避免 need direct evidence; the checker warns about them (C25).

## 2. Default claim set (computer-implemented inventions)

Ten claims are covered by the filing fee; each claim from the 11th onward costs an additional fee (150 CNY per claim under the current schedule), so aim for ≤10 unless the user wants more.

| No. | Type | Content |
|---|---|---|
| 1 | Independent method | Core steps with the distinguishing features |
| 2–6 | Dependent method | One mechanism (fallback position) each; most valuable first |
| 7 | Independent apparatus | Program modules mirroring claim 1's steps one-to-one |
| 8 | Independent electronic device | Processor + memory executing the method of claims 1–6 |
| 9 | Independent storage medium | Medium storing instructions for the method of claims 1–6 |

Adapt for other subject matter: a physical device or system gets structural product claims (components and their connections); a hardware–software system may need a system claim instead of the program-module apparatus. Add a system claim only when the paper describes a system architecture.

## 3. Claim formats

Independent method claim (前序部分 + 其特征在于 + 特征部分; steps separated by semicolons):

```text
1.一种视频配乐生成方法，其特征在于，包括：
获取待配乐视频，对所述待配乐视频进行镜头分割，得到多个镜头片段及各镜头片段的时间边界；
……；
在所述时间边界处对所述分段音频进行交叉淡化拼接，得到所述待配乐视频的配乐音频。
```

(Line breaks above are for readability; in the JSON each claim is one string.)

When the closest prior art shares a clear set of features, a two-part form is also correct: "一种……方法，包括A和B，其特征在于，还包括C；所述B具体为……。"

Dependent claim:

```text
3.根据权利要求1所述的视频配乐生成方法，其特征在于，所述场景描述文本包括情绪标签和节奏强度。
```

Multiple dependent claim (择一引用 only):

```text
6.根据权利要求1至5中任一项所述的视频配乐生成方法，其特征在于，……。
```

Apparatus claim (modules mirror the method; reference numerals in parentheses are optional but must then match the drawing and the description):

```text
7.一种视频配乐生成装置，其特征在于，包括：
镜头分割模块（301），用于获取待配乐视频，对所述待配乐视频进行镜头分割，得到多个镜头片段及各镜头片段的时间边界；
……。
```

Electronic device and storage medium:

```text
8.一种电子设备，其特征在于，包括：至少一个处理器；以及与所述至少一个处理器通信连接的存储器；其中，所述存储器存储有可被所述至少一个处理器执行的指令，所述指令被所述至少一个处理器执行，以使所述至少一个处理器能够执行权利要求1至6中任一项所述的视频配乐生成方法。

9.一种计算机可读存储介质，其特征在于，所述计算机可读存储介质存储有计算机指令，所述计算机指令用于使计算机执行权利要求1至6中任一项所述的视频配乐生成方法。
```

Step numbers (S101) are optional in claims; if used, they must match the flowchart and description.

## 4. Language and form rules

- **Numbering**: Arabic numerals in order, "1." "2." at the start.
- **One period**: each claim ends with one "。" and contains no other "。". Use "；" between steps/modules and "，" inside them.
- **Definite wording**: avoid 厚、薄、强、弱、高温、高压、很宽范围; 例如、最好是、尤其是、必要时; 约、接近、等、或类似物 (审查指南第二部分第二章3.2.2), and also 大约、可能、也许、比如、优选、可以、不限于、若干、某些、基本上. Use "用于" / "被配置为" instead of "可以"; closed lists ("A、B和C中的至少一种") only when the paper supports each member.
- **No references** to the description or figures ("如说明书……所述", "如图1所示") except where absolutely necessary; reference numerals may follow features in parentheses.
- **Formulas** are allowed; define each variable inside the claim ("其中，R(x)表示……").
- **Antecedent basis**: introduce a feature without "所述" ("得到光照图"), then refer back with "所述光照图". In a dependent claim, "所述X" requires X in the claim chain it depends on; a new feature is introduced with "还包括……" and no "所述".
- **Subject consistency**: a dependent claim repeats the subject of the claim it refers to ("根据权利要求1所述的视频配乐生成方法"); it may not change category (a 装置 claim cannot depend on a 方法 claim).
- **Dependency rules**: refer only to earlier claims; a multiple dependent claim refers alternatively (或 / 中任一项) and cannot serve as the basis of another multiple dependent claim (实施细则第25条).
- **Terms** match the description exactly.

`scripts/check_patent_draft.py` tests all of these mechanically, including a heuristic for antecedent basis. Treat its `C14` warnings seriously: they are usually real.

## 5. Support (以说明书为依据)

Each claim feature must appear in the description in the same wording, with enough detail to implement it. Maintain `support_map` in the JSON: for each claim, the paper locations its features come from. A claim whose features you cannot map to the paper is a fidelity problem; fix the claim, not the map.

## 6. Common failures

- Claim 1 is a translation of the paper's whole pipeline, including incidental details (agent roles, full enumerations, round limits) → too narrow; triage and move details down.
- Negative limitations or code field names in claims (checker codes C20, C21).
- Several independent mechanisms merged into one dependent claim (checker C24).
- Claims or effects stated more strongly than the paper's evidence (checker C25).
- Claim 1 is "apply a neural network to X" → no technical contribution; include the actual adaptation.
- Abstract-only data ("获取数据；处理数据") → 客体 risk; name the technical data.
- Dependent claims that add nothing technical ("所述方法由计算机执行") → wasted claims.
- Effects or purposes written as limitations ("以提高准确率") without a structural/step feature → unclear.
- Apparatus modules that do not map one-to-one to method steps → support problems.
- Features drawn from the paper's future-work section → unsupported.
