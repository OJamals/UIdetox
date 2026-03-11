# UIdetox × Codex CLI Integration

## Setup

1. Install UIdetox globally or in your project:
   ```bash
   pip install uidetox
   ```

2. Copy the design skill to Codex's skill directory:
   ```bash
   mkdir -p ~/.codex/skills/uidetox
   cp SKILL.md ~/.codex/skills/uidetox/
   cp -r reference/ ~/.codex/skills/uidetox/
   cp -r commands/ ~/.codex/prompts/
   ```

   Or use the built-in command:
   ```bash
   uidetox update-skill codex
   ```

3. Initialize UIdetox in your project:
   ```bash
   uidetox setup
   ```

## Workflow

```bash
# Scan the codebase for AI slop
uidetox scan --path .

# Fix issues one file at a time
uidetox next

# Or enter the autonomous loop
uidetox loop
```

## Key Commands

| Command | Purpose |
|---------|---------|
| `uidetox scan` | Full audit with static slop detection |
| `uidetox next` | Get next file batch with SKILL.md context |
| `uidetox resolve <id> --note "..."` | Mark issue fixed |
| `uidetox loop` | Autonomous fix loop |
| `uidetox status` | Health dashboard |

See `uidetox --help` for the full command list.
