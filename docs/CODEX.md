# UIdetox × Codex CLI Integration

## Setup

1. Install UIdetox globally or in your project:
   ```bash
   pip install uidetox
   ```

2. Copy the design skill to Codex's skill directory:
   ```bash
   uidetox update-skill codex
   ```

3. Initialize UIdetox in your project:
   ```bash
   uidetox setup
   ```

## Workflow

```bash
# Enter the autonomous loop (full 5-phase protocol)
uidetox loop

# Or scan first, then fix manually
uidetox scan --path .
uidetox next
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `uidetox loop` | Full autonomous loop (scan → fix → review → finalize) |
| `uidetox scan` | Static slop detection + design audit prompt |
| `uidetox next` | Get next component batch with SKILL.md context |
| `uidetox batch-resolve ID1 ID2 --note "..."` | Resolve batch with single coherent commit |
| `uidetox check --fix` | Pre-commit quality gate (tsc → lint → format) |
| `uidetox review` | LLM subjective quality review |
| `uidetox review --score N` | Record subjective score (0-100) |
| `uidetox status` | Blended Design Score (30% static + 70% LLM review) |
| `uidetox memory show` | View session progress and last scan summary |
| `uidetox finish` | Squash-merge session branch |

See `uidetox --help` for the full command list.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
