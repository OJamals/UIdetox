## GitHub Copilot Workspace Integration

GitHub Copilot Workspace operates on spec-driven pull request generation. UIdetox can be used as a pre-flight checklist or a continuous spec constraint.

### 1. Spec Constraint

When defining your Copilot Workspace prompt, explicitly include UIdetox requirements:

```markdown
# Implementation Requirements

This project adheres to the UIdetox anti-slop guidelines. 
1. Read `SKILL.md` before generating any UI components.
2. Avoid generic, AI-generated aesthetics (e.g., system-ui fonts, flat borders, excessive glassmorphism, purple gradients).
3. The resulting PR must successfully pass a `uidetox check` and `uidetox scan` without generating any T2, T3, or T4 issues.
```

### 2. Terminal Integration

If you use Copilot within your CLI or IDE terminal, you can ask Copilot to guide you through the loop:

> @workspace `uidetox status` shows I have 5 pending design issues. Run `uidetox next`, read the batched issues for the highest priority file, and generate the code edits to fix them. Once done, output the `uidetox resolve` commands I need to run.
