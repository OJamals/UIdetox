## Cursor Integration

Cursor natively supports custom rules and subagents. UIdetox leverages Cursor's `.cursor/rules/` and `.cursor/agents/` directories to enforce anti-slop guidelines globally.

### 1. Installation

```bash
uidetox update-skill cursor
```
If you are on Cursor Nightly, ensure Agent Skills is enabled in Settings → Beta, then Settings → Rules.

Create a global `.cursor/rules/uidetox.mdc` file pointing to UIdetox:
```markdown
---
description: UIdetox Anti-Slop Guidelines
globs: *.tsx, *.jsx, *.ts, *.js, *.css
---
Before generating frontend code, ALWAYS cross-reference the anti-patterns listed in `SKILL.md` at the project root. DO NOT output purple-blue gradients, generic Inter typography, or arbitrary glassmorphism.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
```

### 2. The UIdetox Cursor Agent

Define a UIdetox agent in `.cursor/agents/uidetox.md`:

```markdown
---
name: uidetox
description: Eliminates AI slop by running the UIdetox scan→fix loop
tools:
  - run_terminal_command
  - read_file
  - edit_file
---
Your entire job is executing the UIdetox loop. Run `uidetox loop` to bootstrap the full 5-phase autonomous protocol.

The loop will autonomously:
1. Execute mechanical fixes (tsc → lint → format)
2. Scan the codebase with 60+ anti-pattern rules
3. Fix issues component-by-component with injected design context
4. Run subjective quality review and score
5. Continue iterating until Design Score ≥ 95
6. Squash-merge the session branch when complete

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs.
```

Open Cursor Chat, switch to the `uidetox` agent, and type "Start the loop."
