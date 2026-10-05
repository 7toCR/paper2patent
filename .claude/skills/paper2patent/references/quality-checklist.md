# Quality Checklist

Run before delivery and in `review` mode. The first block is automated; the rest needs judgement. Report only what the user needs (open issues, gaps, risks), not the checklist itself.

## A. Automated (`scripts/check_patent_draft.py`)

Covers: claim numbering; one final period; uncertain words; references to the description/figures in claims; dependency direction; 择一 for multiple dependency; multiple-on-multiple dependency; subject/category consistency; antecedent basis (heuristic); invention-name length and wording; abstract length (300 incl. punctuation) and wording; empty description sections; "如权利要求……所述" and paper-style wording in the description; figure numbering vs. 附图说明; abstract figure; reference numerals in drawings vs. text; step numbers in drawings vs. text; `【待补充】` vs. `gaps`; `support_map` coverage.

Zero errors is required. A warning is acceptable only when you can say why it is a false alarm.

## B. Fidelity audit (claim by claim)

For every claim feature, point to the paper location in `support_map`. Then check:

- Nothing in the claims, description or drawings is absent from the paper: no new module, step, parameter, dataset, hardware, application scenario, effect or number.
- Generalisations in claim 1 are backed by the paper (alternatives mentioned, function described generically).
- Effects are the paper's effects, with the paper's numbers, compared against the method the paper compared against.
- Nothing from limitations or future work appears as an embodiment.
- Drawings: every node and edge traceable to the paper's figure or text.

## C. Patent logic

- Claim 1 was triaged feature by feature (`notes.claim_plan`): no organisational detail, complete enumerations, round limits, code field names or negative limitations unless they are the technical contribution.
- Verification/revision/iteration mechanisms in the claims are drawn as loops in the flowchart (checker F10).
- The description contains no drafting remarks (checker D08); evidence boundaries from the paper are stated once, briefly; technical clarifications of what a constraint or state means are kept.
- If the paper has a worked example of the core mechanism, the embodiment walks through it; if not, the handover list asks for one.
- Each separable mechanism has its own dependent claim; no dependent claim bundles independent mechanisms (checker C24).
- Every branch of a generalised claim 1 (alternatives, generic terms) is described in the embodiment; thin branches are flagged in `notes.risks` and the handover list.
- Parameters appear in claims only where the paper shows they matter; wording keeps the paper's strength (checker C25).
- `notes.sufficiency` covers claim 1 and the main dependent claims; every gap is named, none is filled by invention (checker S03).
- Distinguishing features → technical problem → technical effect form one chain that appears consistently in 背景技术, 发明内容 and 具体实施方式.
- Claim 1 contains all necessary features and no incidental ones; dependent claims are real fallback positions, ranked by value.
- Apparatus modules map one-to-one to method steps; device and medium claims refer to the right method claims.
- Technical character is explicit: technical field, technical data, technical effect (`patentability-and-disclosure.md` §3).

## D. Sufficiency and support

- 具体实施方式 explains every claim term and every step with inputs, outputs, formulas and parameters as reported.
- For model-based inventions: modules/layers/connections, training data, loss, optimiser and key hyperparameters, and how inputs/outputs map to the application scene.
- Claim wording appears in the description in the same terms.
- Every figure is referred to in the embodiment; every reference numeral in a figure appears in the text and vice versa.

## E. Form and files

- Five parts present and in order; each starts on a new page; drawings show only "图N" underneath; no source-paper line, notes or gaps list inside the application file.
- Drawings: black and white, readable, no clipped or overlapping labels, no internal titles. You looked at the PNGs and the preview pages.
- The 撰写说明 file contains the disclosure status, risks, claim structure, support map, gaps and drawing sources.
- PDF produced (or the limitation stated).

## F. Message to the user

- Files and what each is.
- Claim 1's core in one or two sentences; the claim structure.
- Disclosure/novelty assessment and any 客体 or data-ethics risk.
- Where the handover checklist is and its key items (ownership, disclosure date, missing technical material).
- Recommendation: review by a patent attorney and a prior-art search before filing.
