# Domain Docs

This repository uses a single-context domain-documentation layout.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root.
- **`docs/adr/`** — read ADRs touching the area being changed.

If these files do not exist, proceed silently. Do not suggest creating them upfront. The `/domain-modeling` skill creates them lazily when terms or decisions get resolved.

## File structure

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

## Use the glossary's vocabulary

When output names a domain concept—issue title, refactor proposal, hypothesis, or test name—use its term from `CONTEXT.md`. Do not drift to synonyms the glossary rejects.

Missing concepts signal invented language or a genuine modeling gap. Reconsider invented language; record genuine gaps for `/domain-modeling`.

## Flag ADR conflicts

If output contradicts an existing ADR, surface it explicitly instead of silently overriding it:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
