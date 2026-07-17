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
   This merges `SKILL.md`, `AGENTS.md`, `commands/`, and `reference/` into `~/.codex/skills/uidetox/` and mirrors the command library into `~/.codex/prompts/uidetox/`. Unrelated files are preserved.

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
| `uidetox status` | Blended Design Score (60% static + 40% LLM review) |
| `uidetox capture` | Capture before/after screenshots and amplified visual diffs. Start your dev server first. |
| `uidetox diff` | Compare fresh analysis against stored baseline (NEW / FIXED / UNCHANGED). |
| `uidetox watch` | Poll a directory for file changes and re-scan automatically. |
| `uidetox memory show` | View session progress and last scan summary |
| `uidetox finish` | Squash-merge session branch |

See `uidetox --help` for the full command list.

## Visual Regression + Port Configuration

Install capture support and Chromium once before first use:

```bash
pip install 'uidetox[capture]'
python -m playwright install chromium
```

```bash
pnpm dev
uidetox capture --stage before
uidetox capture --stage after

# Non-standard port
uidetox capture --stage before --url http://localhost:5173
```

To persist a non-3000 target for `capture`, set `dev_server` in `.uidetox/config.json`:

```json
{
   "dev_server": "http://localhost:5173"
}
```

Resolution order is: `--url` → `.uidetox/config.json` `dev_server` → `http://localhost:3000`.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
