---
description: The UIdetox autonomous loop for eliminating AI slop from full-stack code
---

# UIdetox Autonomous Workflow

## Overview
This workflow sets up the UIdetox Python CLI, performs the initial scans, and then unleashes the agent into a continuous, self-propagating loop to automatically fix all mechanical, design, and integration issues until the codebase achieves a high Design Score.

## Prerequisites
- Ensure the UIdetox CLI is installed (`pip install -e .` from the UIdetox project root).
- Ensure `SKILL.md` is accessible to the agent.

## Steps

### 1. Detect and Check
Run the detection and mechanical checks:
```bash
uidetox detect
uidetox check --fix
```
This will automatically find linters and formatters, fix what it can, and queue remaining mechanical errors as T1 issues.

### 2. Full Codebase Scan
Next, the agent must scan the codebase for design slop and full-stack integration issues:
```bash
uidetox rescan
```
The agent should explore the codebase, check against `SKILL.md` anti-patterns, and queue any findings using `uidetox add-issue`.

### 3. Initiate Autonomous Loop
Run the loop command, which provides the agent with its explicit infinite-loop prompt:
```bash
uidetox loop --target 95
```

### 4. Agent Execution Phase
After running `uidetox loop`, the agent MUST:
1. Stop asking the user for permission.
2. Read the instructions printed by the `loop` command exactly.
3. Rapidly cycle through `uidetox status`, `uidetox next`, writing fixes to files, and `uidetox resolve` in a continuous chain.
4. Auto-resume scanning if the queue is empty but the score is below the target.
5. Exit only when Score >= Target AND the queue is empty.
