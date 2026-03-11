# UIdetox

**The anti-slop engine for AI-generated frontends.**

![UIdetox Flow](uidetox-flow.jpg)

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
This is a closed-loop system. Do not stop after one fix. Repeat this cycle until the strict score is maximized.
Run `uidetox loop` to bootstrap the full 5-phase protocol. The loop will guide you through:
1. Phase 0: Mechanical fixes (`uidetox check --fix`)
2. Phase 1: LLM-dynamic codebase exploration and mapping via GitNexus (`uidetox scan`)
3. Phase 2: Component-level batch fixes (`uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`)
4. Phase 3: Subjective review (`uidetox review` → `uidetox review --score N`)
5. Phase 4: Status check with blended Design Score (`uidetox status`)
6. Phase 5: Finalize (`uidetox finish`)

RULES OF ENGAGEMENT
1. Heavy Lifting: Don't be lazy. Large refactors and small detailed fixes — do both with equal energy. Replace entire components if they reek of AI slop. Fix things properly, not minimally.
2. Subordinate Ego: `uidetox next` injects specific SKILL.md design rules into your context. Follow them strictly. Do not substitute your own analysis or rely on your baseline training data.
3. Orchestrator: For massive codebases, the loop will prompt you to run `uidetox subagent` to spawn parallel observers. Act as a manager.
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
| `uidetox loop` | Enter autonomous protocol (creates session branch, guides scan → fix loop). |
| `uidetox scan` | Full audit: auto-detects tooling and runs 40-rule static analyzer + dynamic prompt. |
| `uidetox next` | Batches the highest-priority component issues with SKILL.md context injection. |
| `uidetox batch-resolve` | Resolves a batch of issues with a single coherent commit |
| `uidetox status` | View your **Blended Design Score** (60% static + 40% LLM review) and hints. |
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