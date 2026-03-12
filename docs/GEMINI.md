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

The loop bootstraps with auto-detected tooling, continuation context from memory, and component-level batch commits. Gemini will:
1. Run `uidetox check --fix` to clear mechanical issues
2. Run `uidetox scan --path .` then systematically read every frontend file
3. Fix issues by component using `uidetox next` → fix all → `uidetox batch-resolve ID1 ID2 ... --note "..."`
4. Run `uidetox review` + `uidetox review --score N` for subjective quality assessment
5. Check `uidetox status` for blended Design Score (30% static + 70% LLM review)
6. Run `uidetox finish` to squash-merge the session branch

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.
