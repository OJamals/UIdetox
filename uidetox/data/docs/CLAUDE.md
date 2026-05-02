## Claude Code Integration

UIdetox is designed to work with Claude Code via direct skill injection.

### 1. Installation

Install the UIdetox skill specifically for Claude:
```bash
uidetox update-skill claude
```
This command copies `SKILL.md`, `commands/`, and `reference/` into `.claude/skills/uidetox/`. Claude Code automatically detects and loads skills from `.claude/skills/`.

### 2. Autonomous Loop (Single Agent)

The simplest way to dispatch Claude into the UIdetox loop:

```bash
uidetox loop
```

This bootstraps the full 5-phase protocol with auto-detected tooling, continuation context from memory, and component-level batch commits. Claude will autonomously:
1. Run `uidetox check --fix` (mechanical fixes)
2. Run `uidetox scan --path .` then systematically read every frontend file (LLM-dynamic analysis)
3. Fix issues component-by-component using `uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`
4. Run `uidetox review` + `uidetox review --score N` to record subjective quality
5. Check `uidetox status` for blended Design Score (60% static + 40% LLM review)
6. Run `uidetox finish` to squash-merge the session branch

Progress is auto-saved to memory. Re-running `uidetox loop` resumes from the last checkpoint.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.

### 3. Orchestrator Mode (Subagents)

For massive codebases, the loop integrates parallel sub-agent exploration (Phase 1.6). Claude can spawn parallel observers:
```bash
uidetox subagent --stage-prompt observe --parallel 3
```
This isolates concerns across five stages (Observe → Diagnose → Prioritize → Fix → Verify) for maximum quality.

### 4. Visual Regression Workflow

Use `uidetox capture` to validate UI changes visually. **Start your dev server first** — UIdetox does not launch it.

```bash
# Step 1: start your dev server
npm run dev          # or pnpm dev, yarn dev, etc.

# Step 2: baseline screenshot before fixes
uidetox capture --stage before

# Step 3: make your UI changes

# Step 4: screenshot after fixes + auto-generates amplified diff
uidetox capture --stage after

# For non-standard ports:
uidetox capture --stage before --url http://localhost:5173

# For responsive breakpoints (320, 768, 1024, 1440):
uidetox capture --stage before --responsive
```

If your app is not on port 3000, either pass `--url` or persist the setting in `.uidetox/config.json`:

```json
{
  "dev_server": "http://localhost:5173"
}
```

URL resolution order is: `--url` → `.uidetox/config.json` `dev_server` → `http://localhost:3000`.

Screenshots and diff images are saved to `.uidetox/snapshots/`. The diff is amplified 8× so subtle pixel changes are clearly visible.

### 5. Issue Diff (Regression Tracking)

Track which rules are newly introduced vs. fixed vs. carried over between sessions:

```bash
uidetox diff                     # compare all files against stored baseline
uidetox diff --since abc123      # only files changed since git SHA
uidetox diff --output github     # GitHub Actions annotation format
uidetox diff --save              # persist fresh analysis as the new baseline
```

### 6. Live Watch Mode

Re-scan automatically whenever a file changes during active development:

```bash
uidetox watch                    # watch current directory, 1s poll interval
uidetox watch --path src/        # limit scope
uidetox watch --interval 2       # poll every 2 seconds
```
