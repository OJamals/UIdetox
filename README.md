# 🧼 UIdetox

**The anti-slop engine for AI-generated frontends.**

[UIdetox](https://github.com/OJamals/UIdetox) is an agent harness that eliminates the "AI smell" from your UI. It transforms generic, LLM-generated code into hand-crafted, high-fidelity interfaces through a systematic **scan → fix loop** that enforces design taste and detects common AI anti-patterns.

[Installation](#-installation) • [The Loop](#-the-loop) • [Commands](#-commands) • [Design Dials](#-design-dials)

---

## ✨ From "Vibe Coding" to "Vibe Design"

AI coding tools are great at building things fast, but the results often scream "AI made this"—Inter font, purple gradients, glassmorphism, and generic hero dashboards. 

**UIdetox** gives your agent a "Design Score" to optimize. It’s not a linter; it’s a standard. By knowing what *not* to do, your agent can finally produce code that makes people ask "Who made this?"—not "Which AI made this?"

---

## 🤖 The Agent Prompt
**Paste this into your AI coding agent (Claude, Cursor, Windsurf, etc.) to begin:**

> I want you to eliminate "AI slop" from this codebase. Your goal is to reach a **Design Score of 95+**.
> 
> 1. **Setup:** Run `pip install uidetox && uidetox update-skill [your_agent_name] && uidetox setup --auto-commit`.
> 2. **Audit:** Run `uidetox scan .` to generate the initial issue queue.
> 3. **The Loop:** Run `uidetox next`. This batches issues for a single file. Fix them holistically using the provided `SKILL.md` rules.
> 4. **Resolve:** After fixing, run `uidetox resolve <ID> --note "Description of design changes"`.
> 5. **Repeat:** Continue running `next` until the queue is empty, then `uidetox rescan` to verify.
>
> **Don't be lazy.** Replace entire components if they reek of AI slop. Use `uidetox polish` or `uidetox animate` for targeted passes.

---

## 🚀 Installation

```bash
pip install uidetox

# Install the design rules for your specific environment:
uidetox update-skill claude    # (Also supports: cursor, gemini, windsurf, copilot)
uidetox setup --auto-commit    # Initializes design dials & git integration
```

---

## 🛠 Commands

### The Engine (CLI)
| Command | Action |
| :--- | :--- |
| `uidetox scan` | Full audit: auto-detects tooling and runs the static slop analyzer. |
| `uidetox next` | Batches the highest-priority issues with design context injection. |
| `uidetox status` | View your **Design Score** and pending issue count. |
| `uidetox loop` | Enter autonomous mode (runs until score target is hit). |
| `uidetox rescan` | Clears queue and re-audits with 18+ fresh anti-slop rules. |

### Design Skills (Slash Commands)
Use these for targeted improvements on specific files or directories:
* `uidetox polish` – Final quality and alignment pass.
* `uidetox animate` – Adds purposeful motion (spring physics, scroll reveals).
* `uidetox audit` – Technical checks for accessibility and performance.
* `uidetox harden` – Edge cases, error handling, and i18n.

---

## 🎛 Design Dials
Control the "aesthetic DNA" of the output by adjusting these values in `uidetox setup`:

* **DESIGN_VARIANCE (1-10):** From clean/centered (1) to asymmetric/massive whitespace (10).
* **MOTION_INTENSITY (1-10):** From CSS-only (1) to complex spring physics and reveals (10).
* **VISUAL_DENSITY (1-10):** From spacious "art gallery" (1) to "cockpit mode" data density (10).

---

## 🚫 The Slop Checklist
UIdetox actively hunts and destroys:
- [ ] Overused **Inter** font stacks.
- [ ] Generic **Purple-Blue** gradients.
- [ ] Identical **Card Grids** with no hierarchy.
- [ ] Meaningless **Glassmorphism**.
- [ ] Default **Lucide/Radix** patterns with zero customization.
- [ ] "Generic Startup" copywriting.

---

### 📜 Credits & License
Built on the shoulders of [desloppify](https://github.com/peteromallet/desloppify) and [impeccable](https://github.com/pbakaus/impeccable)

MIT © [OJamals](https://github.com/OJamals)
