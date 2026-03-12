## Claude Code Integration

UIdetox is designed to work seamlessly with Claude Code (CLI) and Claude Desktop via MCP or direct skill injection.

### 1. Installation

Install the UIdetox skill specifically for Claude:
```bash
uidetox update-skill claude
```
This command copies `SKILL.md`, `AGENTS.md`, `commands/`, and `reference/` into your project's `.claude/skills/uidetox/` directory. Claude Code automatically detects and loads skills from `.claude/`.

### 2. Autonomous Loop (Single Agent)

The simplest way to dispatch Claude into the UIdetox loop:

```bash
uidetox loop
```

This bootstraps the full 5-phase autonomous protocol. Claude will:
1. Execute mechanical fixes (`tsc → lint → format`)
2. Scan the codebase with 60+ anti-pattern rules
3. Fix issues component-by-component with injected design context
4. Run subjective quality review and score
5. Continue iterating until Design Score ≥ 95
6. Squash-merge the session branch when complete

Progress is auto-saved to memory. Re-running `uidetox loop` resumes from the last checkpoint.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.

### 3. Orchestrator Mode (Subagents)

For massive codebases, the loop integrates parallel sub-agent exploration (Phase 1.6). Claude can spawn parallel observers:
```bash
uidetox subagent --stage-prompt observe --parallel 3
```
This isolates concerns across five stages (Observe → Diagnose → Prioritize → Fix → Verify) for maximum quality.
