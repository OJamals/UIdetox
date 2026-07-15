## GitHub Copilot Integration

UIdetox works with GitHub Copilot in VS Code and other Copilot surfaces that can read project-root context.

### 1. Installation

```bash
uidetox update-skill copilot
```

This copies `SKILL.md`, `AGENTS.md`, `commands/`, and `reference/` into the project root. Copilot can then pick up the UIdetox workflow from `SKILL.md` and `AGENTS.md`.

### 2. Prompt Constraint

When defining your Copilot task or workspace prompt, explicitly include UIdetox requirements:

```markdown
# Implementation Requirements

This project adheres to the UIdetox anti-slop guidelines. 
1. Read `SKILL.md` before generating any UI components.
2. Avoid generic, AI-generated aesthetics (e.g., system-ui fonts, flat borders, excessive glassmorphism, purple gradients).
3. The resulting PR must successfully pass `uidetox check` and `uidetox scan` without generating any T2, T3, or T4 issues.
4. **CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
```

### 3. Terminal / Chat Integration

If you use Copilot within your CLI or IDE terminal, dispatch into the full autonomous loop:

```bash
uidetox loop
```

Or guide Copilot manually:

> @workspace Run `uidetox status` to check our Design Score. Then run `uidetox next` to get the next component batch. Fix all issues in a single pass, then run `uidetox batch-resolve ID1 ID2 ... --note "what you changed"` to commit.

### 4. Visual Regression + Dev Server Configuration

Use `uidetox capture` during PR validation or before final handoff. **Start your dev server first** — UIdetox does not launch it.

```bash
# Start your app
pnpm dev      # or npm run dev / yarn dev

# Capture baseline and after state
uidetox capture --stage before
uidetox capture --stage after

# Override a non-standard port for one run
uidetox capture --stage before --url http://localhost:5173
```

To persist a non-3000 target, add this to `.uidetox/config.json`:

```json
{
  "dev_server": "http://localhost:5173"
}
```

Resolution order is: `--url` → `.uidetox/config.json` `dev_server` → `http://localhost:3000`.

### 5. Regression Tracking

```bash
uidetox diff
uidetox diff --since <sha>
uidetox diff --output github
uidetox diff --save
```

Use this to compare fresh analysis against the stored baseline and surface NEW / FIXED / UNCHANGED issues.

### 6. Watch Mode

```bash
uidetox watch
uidetox watch --path src/
uidetox watch --interval 2
```

This is useful when iterating in Copilot Chat while you want the analyzer to keep pace with local edits.
