# Claude Code Instructions

This repository publishes Paper2Patent prompt templates and AI agent skills for converting academic papers into Chinese invention patent application drafts.

## Project Skill

Use `.claude/skills/paper2patent/SKILL.md` when the task involves paper-to-patent conversion, claim drafting, patent specification drafting, patent drawing descriptions, or fidelity checks against a source paper.

## Repository Rules

- Keep generated patent drafts, unpublished papers, invention disclosures, and private user materials out of git.
- Do not add local machine paths, usernames, API keys, tokens, cookies, phone numbers, emails, addresses, or identity numbers to `skills/` or `.claude/skills/`.
- Keep skill instructions concise; move long drafting rules into `references/`.
- Preserve UTF-8 Markdown and the existing Chinese patent terminology.

## Validation

Run skill validation after changes:

```powershell
$env:PYTHONUTF8='1'; python <skill-creator>/scripts/quick_validate.py skills/paper2patent
$env:PYTHONUTF8='1'; python <skill-creator>/scripts/quick_validate.py .claude/skills/paper2patent
git diff --check
```

Smoke-test the scripts on the bundled example (outputs go to a temporary folder outside git):

```bash
mkdir -p /tmp/p2p && cp skills/paper2patent/assets/example_patent_content.json /tmp/p2p/example.json
python skills/paper2patent/scripts/check_patent_draft.py /tmp/p2p/example.json
python skills/paper2patent/scripts/generate_patent_drawings.py /tmp/p2p/example.json -o /tmp/p2p/out --update-json
python skills/paper2patent/scripts/generate_patent_docx.py /tmp/p2p/example.json -o /tmp/p2p/out/example.docx --require-drawings
python skills/paper2patent/scripts/export_patent_pdf.py /tmp/p2p/out/example.docx -o /tmp/p2p/out/example.pdf --preview-dir /tmp/p2p/out/preview
```

Keep `skills/paper2patent/` and `.claude/skills/paper2patent/` identical (`diff -r`).

To judge whether a change improves draft quality, follow `evals/README.md` (fixed conditions, several papers and runs, blind pairwise review with `evals/rubric.md`). Never commit files under `evals/inputs/` or `evals/runs/`.
