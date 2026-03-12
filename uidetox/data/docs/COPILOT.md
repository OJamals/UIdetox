## GitHub Copilot Integration

UIdetox integrates with GitHub Copilot through its native `.github/copilot-instructions.md` project-level instruction file.

### 1. Installation

```bash
uidetox update-skill copilot
```

This command:
- Creates `.github/copilot-instructions.md` with UIdetox anti-slop directives (section-injected, safe for existing files)
- Copies `SKILL.md` and `AGENTS.md` to the project root
- Copies `reference/` and `commands/` directories

Copilot automatically reads `.github/copilot-instructions.md` as project context. The installer uses `<!-- uidetox-skill-begin -->` / `<!-- uidetox-skill-end -->` markers, so running `update-skill copilot` again will update the UIdetox section without affecting other content in the file.

### 2. Spec Constraint

When defining your Copilot Workspace prompt, explicitly include UIdetox requirements:

```markdown
# Implementation Requirements

This project adheres to the UIdetox anti-slop guidelines.
1. Read `SKILL.md` before generating any UI components.
2. Avoid generic, AI-generated aesthetics (e.g., system-ui fonts, flat borders, excessive glassmorphism, purple gradients).
3. The resulting PR must successfully pass `uidetox check` and `uidetox scan` without generating any T2, T3, or T4 issues.
4. **CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
```

### 3. Terminal Integration

If you use Copilot within your CLI or IDE terminal, dispatch into the full autonomous loop:

```bash
uidetox loop
```

Or guide Copilot manually:

> @workspace Run `uidetox status` to check our Design Score. Then run `uidetox next` to get the next component batch. Fix all issues in a single pass, then run `uidetox batch-resolve ID1 ID2 ... --note "what you changed"` to commit.
