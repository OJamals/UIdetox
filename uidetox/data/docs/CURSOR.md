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
```

### 2. The UIdetox Cursor Agent

Instead of a standard prompt, define a UIdetox agent in `.cursor/agents/uidetox.md`:

```markdown
---
name: uidetox
description: Eliminates AI slop by running the UIdetox scan→fix loop
tools:
  - run_terminal_command
  - read_file
  - edit_file
---
Your entire job is executing the UIdetox loop. Run `uidetox scan`, then repeatedly hit `uidetox next`. Fix the batched errors in the topmost file. Run `uidetox resolve <ID> --note "..."` for every fix. Run `uidetox status` to check your Design Score. Do not stop until the score is 95+.
```

Open Cursor Chat, switch to the `uidetox` agent, and type "Start the loop."
