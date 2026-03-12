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

This bootstraps the full 5-phase protocol with auto-detected tooling, continuation context from memory, and component-level batch commits. Claude will autonomously:
1. Run `uidetox check --fix` (mechanical fixes)
2. Run `uidetox scan --path .` then systematically read every frontend file (LLM-dynamic analysis)
3. Fix issues component-by-component using `uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`
4. Run `uidetox review` + `uidetox review --score N` to record subjective quality
5. Check `uidetox status` for blended Design Score (30% static + 70% LLM review)
6. Run `uidetox finish` to squash-merge the session branch

Progress is auto-saved to memory. Re-running `uidetox loop` resumes from the last checkpoint.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.

### 3. Orchestrator Mode (Subagents)

For massive codebases, the loop integrates parallel sub-agent exploration (Phase 1.6). Claude can spawn parallel observers:
```bash
uidetox subagent --stage-prompt observe --parallel 3
```
This isolates concerns across five stages (Observe → Diagnose → Prioritize → Fix → Verify) for maximum quality.
