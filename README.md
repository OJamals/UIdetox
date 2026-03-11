# UIdetox

**The anti-slop engine for AI-generated frontends.**

[UIdetox](https://github.com/OJamals/UIdetox) is an agent harness that eliminates the "AI smell" from your UI. It transforms generic, LLM-generated code into hand-crafted, high-fidelity interfaces through a systematic **scan → fix loop** that enforces design taste and detects common AI anti-patterns.

[Installation](#installation) • [Commands](#commands) • [Design Dials](#design-dials)

---

## From "Vibe Coding" to "Vibe Design"

AI coding tools are great at building things fast, but the results often scream "AI made this"—Inter font, purple gradients, glassmorphism, and generic hero dashboards. 

**UIdetox** gives your agent an objective "Design Score" to optimize. It’s not a linter; it’s a standard. By knowing what *not* to do, your agent can finally produce code that makes people ask "Who made this?"—not "Which AI made this?"

---

## The Agent Prompt

**Paste this into your AI coding agent (Cursor, Windsurf, Claude, etc.) to begin:**

```text
I want you to eliminate "AI slop" from this codebase and make the UI indistinguishable from hand-crafted design. Your goal is to reach a **Design Score of 95+**.

To do this, use the UIdetox ecosystem (requires Python 3.11+). Run the following setup:
pip install uidetox
uidetox update-skill [your_agent_name]  # e.g., claude, cursor, windsurf, gemini
uidetox setup --auto-commit

THE LOOP
This is a closed-loop system. Do not stop after one fix. Repeat this cycle until the strict score is maximized:
1. Audit: Run `uidetox scan .` to queue anti-patterns.
2. Fix: Run `uidetox next`. This batches issues for the highest-priority file. Fix them holistically (including fullstack boundaries). 
3. Resolve: Run `uidetox resolve <ID> --note "What you changed"`.
4. Verify: Run `uidetox check --fix` to auto-commit formatting and catch/queue any new mechanical regressions incrementally.
5. Loop: Run `uidetox next` again.
6. Deep Verification: When the queue empties, run `uidetox rescan` to re-audit with fresh eyes. Keep looping until `uidetox status` shows Score >= 95.
7. Finish: Once the target score is reached, run `uidetox finish` to squash the aesthetic fixes cleanly onto your main branch!

RULES OF ENGAGEMENT
1. Heavy Lifting: Don't be lazy. Large refactors and small detailed fixes — do both with equal energy. Replace entire components if they reek of AI slop. Fix things properly, not minimally.
2. Subordinate Ego: `uidetox next` injects specific SKILL.md design rules into your context. Follow them strictly. Do not substitute your own analysis or rely on your baseline training data.
3. Orchestrator Mode: For complex passes, use `uidetox loop --orchestrator`. Act as a manager: generate prompts with `uidetox subagent`, delegate to parallel subagents, and use MCP (Model Context Protocol) servers to read the filesystem and execute terminal commands directly.
```

---

## Installation

```bash
pip install uidetox

# Install the design rules for your specific environment:
uidetox update-skill claude    # (Also supports: cursor, gemini, windsurf, copilot)
uidetox setup --auto-commit    # Initializes design dials & git integration
```

---

## Commands

### The Engine (CLI)
| Command | Action |
| :--- | :--- |
| `uidetox scan` | Full audit: auto-detects tooling and runs the 40-rule static slop analyzer. |
| `uidetox next` | Batches the highest-priority issues with dial-calibrated design context injection. |
| `uidetox status` | View your **Design Score** and actionable per-category hints. |
| `uidetox loop` | Enter autonomous mode (creates a session branch and loops fixes). |
| `uidetox rescan` | Clears queue and re-audits with 40+ fresh anti-slop rules. |
| `uidetox finish` | Squash merges the autonomous session branch cleanly. |

### Design Skills (Slash Commands)
Use these for targeted improvements on specific files or directories:
* `uidetox polish` – Final quality and alignment pass.
* `uidetox animate` – Adds purposeful motion (spring physics, scroll reveals).
* `uidetox audit` – Technical checks for accessibility and performance.
* `uidetox harden` – Edge cases, error handling, and i18n.

---

## Design Dials
Control the "aesthetic DNA" of the output by adjusting these values in `uidetox setup`:

* **DESIGN_VARIANCE (1-10):** From clean/centered (1) to asymmetric/massive whitespace (10). Drives structural layout generation patterns (Bento grids vs split-screens).
* **MOTION_INTENSITY (1-10):** From CSS-only (1) to complex spring physics and reveals (10).
* **VISUAL_DENSITY (1-10):** From spacious "art gallery" (1) to "cockpit mode" data density (10).

---

## The Slop Checklist
UIdetox actively hunts and destroys:

- [ ] Use of **Emojis** in text content
- [ ] Overused **Inter** font stacks.
- [ ] Generic **Purple-Blue** gradients.
- [ ] Identical **Card Grids** with no hierarchy.
- [ ] Meaningless **Glassmorphism**.
- [ ] Default **Lucide/Radix** patterns with zero customization.
- [ ] "Generic Startup" copywriting (e.g. "Next-Gen", "Elevate").
- [ ] **Div Soup** over semantic HTML.
- [ ] Missing **Focus/Hover** accessibility states.

---

### Credits & License
Built on the shoulders of [desloppify](https://github.com/peteromallet/desloppify) and [impeccable](https://github.com/pbakaus/impeccable)

MIT © [OJamals](https://github.com/OJamals)