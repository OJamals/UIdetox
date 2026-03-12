## Gemini Integration

UIdetox works well with Google's Gemini models (via Gemini CLI, Google AI Studio, or GCP Vertex).

### 1. Installation

Run:
```bash
uidetox update-skill gemini
```

Because Gemini CLI uses a persistent configuration file, ensure your project's `GEMINI.md` (or equivalent context file) explicitly references the UIdetox SKILL:
```markdown
@./SKILL.md

# UI Directives
You are enforcing the Anti-Slop catalog defined in SKILL.md. Do not generate generic startup UI.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
```

### 2. Autonomous Loop

Run `uidetox loop` to dispatch Gemini into the full 5-phase protocol:

```bash
uidetox loop
```

The loop bootstraps the full 5-phase autonomous protocol. Gemini will:
1. Execute mechanical fixes (tsc → lint → format)
2. Scan the codebase with 60+ anti-pattern rules
3. Fix issues component-by-component with injected design context
4. Run subjective quality review and score
5. Continue iterating until Design Score ≥ 95
6. Squash-merge the session branch when complete

Operating contract for Gemini during the loop:
- Treat UIdetox as a closed-loop system: `scan → fix → verify → rescan` until the score target is achieved.
- Use the full toolchain, including terminal commands, screenshots/browser checks when relevant, parallel subagents, and MCP systems such as GitNexus.
- You have permission for heavy lifting: large refactors and tiny detail fixes should both be executed with equal energy.
- Fix root causes properly, not minimally.
- If loop, scan, or subagent output gives concrete instructions, follow them exactly instead of replacing them with your own shortcut analysis.

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.
