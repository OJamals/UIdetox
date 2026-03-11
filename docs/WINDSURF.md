## Windsurf Integration

UIdetox integrates deeply into Windsurf's cascading rules and memory systems.

### 1. Installation

Run:
```bash
uidetox update-skill windsurf
```
Because Windsurf uses Global Rules and Workspace Rules, we recommend placing the core UIdetox directives into `.windsurfrules`:

```markdown
# UI Directives (Anti-Slop)
Before writing any frontend code (React, Vue, HTML/CSS), you MUST refer to `SKILL.md` to avoid generic AI aesthetics.
Specifically: DO NOT use purple/blue default gradients, Inter fonts, or bouncy excessive animations. Adhere to the Design Variance, Motion Intensity, and Visual Density scores defined in `.uidetox/config.json`.

**CRITICAL REQUISITE:** Ensure all generated output is strictly type-safe. You MUST conform exactly to pre-existing backend architectures, API contracts, database schemas, and DTOs. Do NOT hallucinate new endpoints or alter data structures when fixing UI slop.
```

### 2. Autonomous Loop

Run `uidetox loop` to dispatch Windsurf's Cascade into the full 5-phase protocol:

```bash
uidetox loop
```

The loop guides the agent through:
1. Mechanical fixes (`uidetox check --fix`)
2. LLM-dynamic codebase exploration + design audit (`uidetox scan`)
3. Component-level batch fixes (`uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`)
4. Subjective review with blended Design Score (`uidetox review` → `uidetox status`)
5. Finalize (`uidetox finish`)

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.
