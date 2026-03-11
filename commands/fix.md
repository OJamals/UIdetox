---
name: fix
description: Interactive fix loop. Picks the next highest-priority issue from a scan, applies the fix, verifies it, and moves on. Repeat until the queue is empty.
args:
  - name: issue
    description: Specific issue ID to fix (optional — picks next priority if omitted)
    required: false
---

Work through the scan issue list one by one. This is Phase 3 of the UIdetox loop.

**First**: Read and apply the full SKILL.md for design principles and engineering rules.

## Prerequisites

A `/scan` must have been run first. If no scan results exist, run `/scan` before proceeding.

## The Fix Loop

```
1. Pick the next issue (or the specified issue ID)
2. Read the diagnostic detail
3. Apply the fix
4. Verify the fix doesn't break functionality
5. Mark the issue resolved
6. Report what was fixed and move to the next issue
```

## Fix Process

### 1. Select Issue
- If no issue ID specified, pick the highest-priority unresolved issue
- Follow the recommended fix order from SKILL.md Section 7:
  1. Font swap (T1)
  2. Color palette cleanup (T1-T2)
  3. Hover and active states (T1-T2)
  4. Layout and spacing (T2)
  5. Replace generic components (T2-T3)
  6. Add loading, empty, and error states (T2)
  7. Polish typography scale and spacing (T2-T3)

### 2. Apply Fix
- Make the minimum change needed to resolve the issue
- Follow the design rules in SKILL.md — don't introduce new anti-patterns while fixing old ones
- Use the appropriate specialized command if the fix is complex:
  - Typography issues → apply SKILL.md Rule 1
  - Color issues → `/colorize` or apply SKILL.md Rule 2
  - Layout issues → apply SKILL.md Rule 3
  - Motion issues → `/animate`
  - Resilience issues → `/harden`
  - Complexity issues → `/distill`
  - Design system alignment → `/normalize`

### 3. Verify
- Confirm the fix resolves the specific issue
- Confirm no regressions were introduced
- Confirm the fix follows SKILL.md rules

### 4. Report
For each fix, report:
- **Issue ID**: Which issue was fixed
- **What changed**: Brief description
- **Files modified**: List of changed files
- **Status**: Resolved / Partially resolved / Deferred (with reason)

### 5. Next
- Show remaining issue count by tier
- Suggest the next issue to fix
- If queue is empty, recommend running `/scan` again to catch cascade effects

## Rules

- Fix one issue at a time. Don't batch unrelated changes.
- Don't break existing functionality.
- Don't introduce new anti-patterns while fixing existing ones.
- Keep changes small and reviewable.
- If a fix requires a T4 (major redesign), flag it for user decision before proceeding.
- Score may temporarily appear worse after fixes — cascade effects are normal, keep going.
