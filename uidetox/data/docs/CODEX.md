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
```

The loop bootstraps the full 5-phase autonomous protocol. Codex will:
1. Execute mechanical fixes (tsc → lint → format)
2. Scan the codebase with 60+ anti-pattern rules
3. Fix issues component-by-component with injected design context
4. Run subjective quality review and score
5. Continue iterating until Design Score ≥ 95
6. Squash-merge the session branch when complete

Operating contract for Codex during the loop:
- Treat UIdetox as a closed-loop system: `scan → fix → verify → rescan` until the score target is achieved.
- Use the full toolchain, including terminal commands, screenshots/browser checks when relevant, parallel subagents, and MCP systems such as GitNexus.
- You have permission for heavy lifting: large refactors and tiny detail fixes should both be executed with equal energy.
- Fix root causes properly, not minimally.
- If loop, scan, or subagent output gives concrete instructions, follow them exactly instead of replacing them with your own shortcut analysis.

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
