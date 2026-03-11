# UIdetox

An agent harness that eliminates "AI slop" from frontend code and enforces quality across frontend, backend, and database layers. It combines design taste enforcement, anti-pattern detection, mechanical linting, and structured remediation into a repeatable scan→fix loop.

UIdetox is created as an effective agent harness for UI/frontend work by serving as an amalgamation of four pioneering projects:
- **desloppify** — The original inspiration for systematic AI-slop removal and workflow automation
- **taste-skill** — Generative design rules, creative arsenal, and motion engine
- **Uncodixfy** — Comprehensive anti-AI-aesthetic pattern catalog
- **impeccable** — Frontend design commands, references, and quality guidelines

## 1. Philosophy

AI-generated UI has a recognizable aesthetic: Inter font, purple-blue gradients, glassmorphism cards, hero metric dashboards, bounce animations, gray text on colored backgrounds. These patterns emerge because LLMs follow the path of least resistance through their training data.

UIdetox fights that bias. Its instructions teach the agent what NOT to do (anti-patterns), what TO do instead (design engineering), and HOW to apply fixes systematically (the loop).

The goal is frontend code that makes someone ask "how was this made?" — not "which AI made this?"

## 2. The Loop

Run `uidetox scan` on the project. The scan auto-detects tooling (TypeScript, biome/eslint/prettier, backend frameworks, database ORMs, API layers) and guides the agent through four steps:

**Step 1 — Mechanical Checks:** Run `uidetox check` to execute tsc → lint → format in sequence. Errors are automatically queued as T1 issues.

**Step 1.5 — Static Slop Analysis:** A 18-rule deterministic analyzer scans all frontend files for known AI anti-patterns (glassmorphism, purple-blue gradients, bounce animations, oversized shadows, gray-on-color text, missing dark mode, etc.). Detected violations are auto-queued with appropriate tiers.

**Step 2 — Design Audit:** The agent reads frontend files and evaluates against SKILL.md. For each issue found:
`uidetox add-issue --file <path> --tier <T1-T4> --issue <description> --fix-command <command>`

**Step 3 — Full-Stack Integration:** If backend/database/API layers are detected, the agent checks for DTO mismatches, schema misalignment, missing error states, and type safety gaps across boundaries.

The issues cover:
- TypeScript compilation errors
- Lint and formatting violations
- Anti-pattern detection (AI slop fingerprints)
- Typography audit
- Color and contrast review
- Layout and spacing analysis
- Motion and interaction quality
- Responsiveness
- Accessibility
- Frontend→Backend→Database integration
- Code quality

The scan generates a prioritized issue list. Issues are tiered:
- **T1**: Quick fix (font swap, color replacement, spacing adjustment)
- **T2**: Targeted refactor (component pattern replacement, state additions)
- **T3**: Design judgment call (layout restructure, interaction rethinking)
- **T4**: Major redesign (full section or page overhaul)

### Phase 2: Plan — decide what to fix first

Run `uidetox plan` to view the queue. The recommended fix order:

1. Font swap — biggest instant improvement, lowest risk
2. Color palette cleanup — remove clashing or oversaturated colors
3. Hover and active states — makes the interface feel alive
4. Layout and spacing — proper grid, max-width, consistent padding
5. Replace generic components — swap cliché patterns for modern alternatives
6. Add loading, empty, and error states — makes it feel finished
7. Polish typography scale and spacing — the premium final touch

### Phase 3: Execute — fix issues file by file

Run `uidetox next`. The CLI batches all pending issues for the highest-priority file and injects relevant SKILL.md design rules directly into the output.
1. Read the file and all issues listed
2. Follow the injected SKILL.md context rules for each issue type
3. Fix ALL issues in one pass (including DTO/Schema alignment if fullstack is detected)
4. Verify the fixes don't break functionality
5. Run `uidetox resolve <issue_id> --note "what you changed"` for each issue
6. Run `uidetox check --fix` to verify mechanical quality and queue new errors incrementally
7. Run `uidetox next` to loop (self-propagating).

Use the design skills directly from the CLI for targeted work:
- `uidetox normalize <target>` for design system alignment
- `uidetox polish <target>` for final quality pass
- `uidetox animate <target>` for motion work
- `uidetox colorize <target>` for color introduction
- `uidetox harden <target>` for edge cases and resilience
- `uidetox distill <target>` for simplification
- See full command list below

### Phase 4: Verify — confirm improvement

Run `uidetox rescan` to clear old issues and re-audit the project. `rescan` automatically runs the 18-rule static slop analyzer and queues any detected anti-patterns before the agent begins its fresh design audit. Run `uidetox status` to see your Design Score. The interface should now:
- Pass the AI Slop Test (no obvious AI tells)
- Have consistent typography with intentional font choices
- Use a cohesive, non-generic color palette
- Have proper interaction states (hover, focus, active, loading, error, empty)
- Be responsive and accessible
- Feel designed, not generated

## 3. Skills

The combined SKILL.md contains the full design knowledge base. It is structured as:

| Section | Source | Purpose |
|---------|--------|---------|
| Design Direction | impeccable | Bold aesthetic commitment |
| Design Engineering | taste-skill | Bias-correcting rules (typography, color, layout, materiality, states) |
| Anti-Pattern Catalog | Uncodixfy + impeccable + taste-skill | Comprehensive list of banned AI UI patterns |
| Creative Arsenal | taste-skill | Advanced design concepts for premium output |
| Motion Engine | taste-skill | Perpetual micro-interaction framework |
| Output Enforcement | taste-skill | Anti-laziness rules for complete code generation |
| Redesign Protocol | taste-skill | Audit-first upgrade workflow |
| Color Palettes | Uncodixfy | Curated dark/light color schemes |

Reference files in `reference/` provide deep-dive guidance for each design domain.

## 4. Commands

### Python CLI Commands (the loop engine)

| Command | Purpose |
|---------|---------|
| `uidetox setup` | Initialize project config and design dials (use `--auto-commit` to enable Git tracking) |
| `uidetox scan` | Full audit: auto-detect tooling → static analyzer → design review |
| `uidetox detect` | Auto-discover linters, formatters, tsc, backend, database, API |
| `uidetox check` | Run tsc → lint → format in sequence, queue errors as T1 (use `--fix` to auto-solve) |
| `uidetox tsc` | Run TypeScript compiler, parse and queue errors |
| `uidetox lint` | Run detected linter (biome/eslint), parse and queue errors |
| `uidetox format` | Run detected formatter (biome/prettier), auto-fix with --fix |
| `uidetox add-issue` | Queue a detected issue with tier and fix command |
| `uidetox plan` | View and reorder the issue queue by priority |
| `uidetox next` | Batch issues for top-priority file with SKILL.md context injection |
| `uidetox resolve <id> --note "..."` | Mark an issue as fixed (note is mandatory) |
| `uidetox loop` | Enter autonomous self-propagation fix loop |
| `uidetox loop --orchestrator` | Sub-agent mode with auto-parallel (1-5) and memory injection |
| `uidetox subagent` | Manage sub-agent sessions and generate stage prompts |
| `uidetox memory` | Read/write persistent agent memory (patterns, notes, reviewed files) |
| `uidetox history` | View run history and score progression (use `--full` for deep inspection) |
| `uidetox status` | Health dashboard with Design Score (1-100) (use `--json` for automation) |
| `uidetox show [pattern]` | Filter/inspect issues by file, tier, or ID |
| `uidetox autofix` | Batch all safe T1 fixes for the agent to apply (use `--dry-run` to preview only) |
| `uidetox rescan` | Clear queue, run 18-rule static analyzer, re-audit from scratch |
| `uidetox finish` | Squash merges the autonomous session branch cleanly |
| `uidetox exclude <path>` | Skip a directory during scanning |
| `uidetox review` | Prompt a subjective UX quality review |
| `uidetox update-skill <agent>` | Install SKILL.md, AGENTS.md, commands/, reference/ for claude/cursor/gemini/codex/windsurf/copilot |
| `uidetox viz` | Generate an HTML heatmap of codebase issues |
| `uidetox tree` | Print a terminal tree of codebase issue density |
| `uidetox zone` | Show/set/clear file zone classifications (production, test, vendor, etc.) |
| `uidetox suppress` | Permanently silence issues matching a pattern |

### Slash Commands (design skills — natively executable via CLI)

| Command | Purpose |
|---------|---------|
| `uidetox audit [target]` | Technical quality checks (a11y, perf, theming, responsive) |
| `uidetox critique [target]` | UX design review (hierarchy, emotion, composition) |
| `uidetox normalize [target]` | Align with design system standards |
| `uidetox polish [target]` | Final pre-ship quality pass |
| `uidetox distill [target]` | Strip to essence, remove complexity |
| `uidetox clarify [target]` | Improve unclear UX copy |
| `uidetox optimize [target]` | Performance improvements |
| `uidetox harden [target]` | Error handling, i18n, edge cases |
| `uidetox animate [target]` | Add purposeful motion |
| `uidetox colorize [target]` | Introduce strategic color |
| `uidetox bolder [target]` | Amplify boring designs |
| `uidetox quieter [target]` | Tone down overly bold designs |
| `uidetox delight [target]` | Add moments of joy |
| `uidetox extract [target]` | Pull into reusable components |
| `uidetox adapt [target]` | Adapt for different devices |
| `uidetox onboard [target]` | Design onboarding flows |

Slash commands are dynamically loaded from `commands/*.md` and accept an optional target argument (e.g., `uidetox audit src/components/`, `uidetox polish checkout-form`).

## 5. Configuration

The harness supports three design dials that control output aesthetic:

**DESIGN_VARIANCE** (1-10) — How experimental the layout is.
- 1-3: Clean, centered, standard grids
- 4-7: Overlapping elements, varied sizes, offset margins
- 8-10: Asymmetric, masonry, massive whitespace zones

**MOTION_INTENSITY** (1-10) — How much animation.
- 1-3: CSS hover/active states only
- 4-7: Fade-ins, smooth transitions, staggered entry
- 8-10: Scroll-triggered reveals, spring physics, magnetic effects

**VISUAL_DENSITY** (1-10) — How much content per screen.
- 1-3: Art gallery mode, spacious, luxury feel
- 4-7: Standard web app spacing
- 8-10: Cockpit mode, dense data, monospace numbers

Default baseline: `(8, 6, 4)`. Override via `/setup` or direct instruction.

## 6. Prerequisite & Provider Installation

```bash
pip install uidetox
```

Then install the design skill for your agent. `update-skill` physically copies all files (SKILL.md, AGENTS.md, commands/, reference/) to the correct location for each platform:

```bash
uidetox update-skill claude     # → .claude/skills/uidetox/
uidetox update-skill cursor     # → project root + .cursor/rules/uidetox.mdc
uidetox update-skill gemini     # → project root + GEMINI.md with @./SKILL.md
uidetox update-skill codex      # → ~/.codex/skills/uidetox/ + ~/.codex/prompts/
uidetox update-skill windsurf   # → project root + .windsurfrules
uidetox update-skill copilot    # → project root (SKILL.md + AGENTS.md)
```

Each agent also receives a tailored integration guide from the `docs/` catalog with platform-specific autonomous loop prompts and orchestrator instructions.

## 7. Repository Structure

```
UIdetox/
├── pyproject.toml                # Python packaging
├── AGENTS.md                     # This file — master agent entry point
├── SKILL.md                      # Combined design skill (all source repos)
├── README.md                     # User documentation + quick-start prompt
├── uidetox/                      # Python CLI package
│   ├── cli.py                    # Argparse router (30+ commands, dynamic slash-command loading)
│   ├── state.py                  # Issue queue + config in .uidetox/
│   ├── tooling.py                # Auto-detection (tsc, biome, eslint, NestJS, etc.)
│   ├── analyzer.py               # 18-rule static slop detector (deterministic anti-pattern scan)
│   ├── history.py                # Run snapshot storage and progression tracking
│   ├── memory.py                 # Persistent agent memory (reviewed files, patterns, notes)
│   ├── subagent.py               # Sub-agent session infrastructure (5-stage pipeline)
│   ├── data/                     # Bundled assets (shipped inside the pip wheel)
│   │   ├── SKILL.md, AGENTS.md   # Design skill + agent entry point
│   │   ├── commands/*.md          # 19 slash command definitions
│   │   ├── reference/*.md         # 10 deep-dive design reference files
│   │   └── docs/*.md              # 6 provider integration guides
│   └── commands/                 # Command implementations
│       ├── scan.py, next.py, resolve.py, plan.py
│       ├── setup.py, review.py, update_skill.py
│       ├── status.py, show.py, autofix.py, loop.py, finish.py
│       ├── exclude.py, rescan.py, add_issue.py
│       ├── detect.py, check.py, tsc.py, lint.py, format_cmd.py
│       ├── subagent_cmd.py, history_cmd.py
│       ├── memory_cmd.py, skill_cmd.py
│       ├── viz.py, zone.py, suppress.py
├── commands/                     # Slash commands (source — copied to data/ at build)
├── reference/                    # Design references (source — copied to data/ at build)
├── docs/                         # Provider guides (source — copied to data/ at build)
├── .agents/workflows/
│   └── detox.md                  # Guided workflow
```
