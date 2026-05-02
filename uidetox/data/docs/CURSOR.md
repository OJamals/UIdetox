## Cursor Integration

Cursor natively supports custom rules and subagents. UIdetox leverages Cursor's `.cursor/rules/` and `.cursor/agents/` directories to enforce anti-slop guidelines globally.

### 1. Installation

```bash
uidetox update-skill cursor
```
This copies `SKILL.md`, `AGENTS.md`, `commands/`, and `reference/` into the project root and auto-generates `.cursor/rules/uidetox.mdc`.

If you are on Cursor Nightly, ensure Agent Skills is enabled in Settings → Beta → Agent Skills.

### 2. Optional Custom Cursor Agent

If you want a dedicated `uidetox` agent persona in Cursor, create `.cursor/agents/uidetox.md`:

```markdown
---
name: uidetox
description: Eliminates AI slop by running the UIdetox scan→fix loop
tools:
  - run_terminal_command
  - read_file
  - edit_file
---
Your entire job is executing the UIdetox loop. Run `uidetox loop` to bootstrap the full 5-phase protocol.

The loop will guide you through:
1. Mechanical fixes (`uidetox check --fix`)
2. LLM-dynamic codebase exploration and design audit (`uidetox scan`)
3. Component-level batch fixes (`uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`)
4. Subjective review (`uidetox review` → `uidetox review --score N`)
5. Status check with blended Design Score (`uidetox status`)
6. Finalize (`uidetox finish`)

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs.
```

The generated `.cursor/rules/uidetox.mdc` already activates the UIdetox rules on frontend files; the custom agent file is optional.

Open Cursor Chat, switch to the `uidetox` agent, and type "Start the loop." if you created the optional agent.

### 3. Visual Regression + Port Configuration

Use `uidetox capture` when validating a redesigned surface. **Start your dev server first** — UIdetox does not launch it.

```bash
pnpm dev
uidetox capture --stage before
uidetox capture --stage after

# Non-standard port
uidetox capture --stage before --url http://localhost:5173
```

To persist the target URL for future runs, add this to `.uidetox/config.json`:

```json
{
  "dev_server": "http://localhost:5173"
}
```

Resolution order is: `--url` → `.uidetox/config.json` `dev_server` → `http://localhost:3000`.

### 4. Diff + Watch Utilities

```bash
uidetox diff
uidetox diff --since <sha>
uidetox watch
uidetox watch --path src/
```

Use `diff` to track regressions against the stored baseline and `watch` to re-scan continuously while Cursor edits files.
