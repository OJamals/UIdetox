# UIdetox

An agent harness that eliminates "AI slop" from frontend code and enforces quality across frontend, backend, and database layers. It combines design taste enforcement, anti-pattern detection, mechanical linting, and structured remediation into a repeatable scan→fix loop.

UIdetox is created as an effective agent harness for UI/frontend work by serving as an amalgamation of four pioneering projects:
- **desloppify** — The original inspiration for systematic AI-slop removal and workflow automation
- **impeccable** — Frontend design commands, references, and quality guidelines

## 1. Philosophy

AI-generated UI has a recognizable aesthetic: Inter font, purple-blue gradients, glassmorphism cards, hero metric dashboards, bounce animations, gray text on colored backgrounds. These patterns emerge because LLMs follow the path of least resistance through their training data.

UIdetox fights that bias. Its instructions teach the agent what NOT to do (anti-patterns), what TO do instead (design engineering), and HOW to apply fixes systematically (the loop).

The goal is frontend code that makes someone ask "how was this made?" — not "which AI made this?"

## 2. The Autonomous Loop

Run `uidetox loop` to bootstrap the full 5-phase protocol. The loop automatically orchestrates the following flow, guiding the agent step-by-step:

### Phase 0: Mechanical Checks
The loop triggers `uidetox check --fix` to execute tsc → lint → format in sequence. Errors are automatically queued as T1 issues and auto-fixed where possible.

### Phase 1: Exploration & Audit (The Scan)
The loop auto-detects tooling (TypeScript, biome/eslint/prettier, backend frameworks, database ORMs, API layers) and performs:
- **Static Slop Analysis:** A 60+ rule deterministic analyzer scans all frontend files for known AI anti-patterns (glassmorphism, purple-blue gradients, bounce animations, oversized shadows, gray-on-color text, missing dark mode, etc.).
- **Design Audit:** The agent reads frontend files and evaluates against SKILL.md.
- **Full-Stack Integration:** If backend/database/API layers are detected, the agent checks for DTO mismatches, schema misalignment, missing error states, and type safety gaps across boundaries. **CRITICAL:** When generating or fixing code, the agent MUST enforce strict type safety and conform perfectly to existing backend architectures, API contracts, and database DTOs.
- **Queue Hygiene:** Scan deduplicates issues already pending in the queue, tightening severity/guidance instead of flooding the backlog with duplicates across repeated passes.

The issues cover TypeScript errors, anti-pattern detection, typography, color/contrast, motion, and backend integration. Issues are tiered T1 (quick fix) to T4 (major redesign).

### Phase 2: Component-Level Fixes
The loop repeatedly triggers `uidetox next`. The CLI batches all pending issues for the highest-priority **component/directory** and injects relevant SKILL.md design rules directly into the context.
1. Read ALL files in the component that have issues
2. Follow the injected SKILL.md context rules for each issue type
3. Fix ALL issues in one pass
4. Use targeted design skills as needed (`uidetox polish <target>`, `uidetox animate <target>`, etc.)
5. Batch-resolve the issues with a single coherent commit: `uidetox batch-resolve ID1 ID2 ... --note "what you changed"`
(The loop auto-saves progress to memory, so `uidetox loop` can resume anywhere if interrupted).

### Phase 3: Subjective Review
The loop spawns 14 parallel domain-specific subagents (2 waves of 7) for comprehensive subjective analysis across 138 total points:

**Wave 1 — Visual Design & Interaction (7 domains):**
1. **Typography & Type Hierarchy** (10 pts) — font families, weight spectrum, type scale, line-height
2. **Color & Contrast** (8 pts) — palette cohesion, contrast ratios, dark mode, AI slop gradients
3. **Interaction & Component States** (10 pts) — hover/focus/active/disabled/loading/empty/error states
4. **Content & UX Writing** (5 pts) — microcopy quality, placeholder data, tone consistency
5. **Motion & Animation Design** (7 pts) — transition timing, easing curves, entrance/exit choreography
6. **Design Elegance & Craft** (10 pts) — holistic aesthetic quality, visual harmony, micro-details, professional finishing
7. **Accessibility & Inclusive Design** (10 pts) — WCAG 2.2 AA, landmarks, keyboard nav, screen reader UX

**Wave 2 — System & Architecture (7 domains):**
8. **Spatial Design & Layout** (15 pts) — grid systems, whitespace rhythm, spacing scale, responsive
9. **Materiality & Surfaces** (7 pts) — shadow craft, border usage, glassmorphism detection
10. **Design System & Consistency** (15 pts) — unified tokens, variant drift, duplication detection
11. **Identity & Brand Coherence** (15 pts) — intentional aesthetic, AI slop fingerprints, visual voice
12. **Responsive Design & Code Architecture** (8 pts) — component structure, file organization, z-index
13. **API & Data Coherence** (10 pts) — DTO alignment, data flow, error/loading/empty states vs. real API behavior
14. **Performance & Web Vitals** (8 pts) — LCP/CLS/INP targets, bundle optimization, lazy loading, image optimization

Each subagent runs `npx gitnexus analyze` and `npx gitnexus query` for codebase intelligence, then scores its assigned domain(s) against the reference files. After all 14 subagents complete, `uidetox check --fix` runs to verify code cleanliness, partial scores are summed, normalized to 0-100, and `uidetox review --score <N>` records the combined score.

**Scoring is deliberately harsh:** a diminishing-returns curve compresses raw scores above 60 (raw 80 → effective ~68, raw 90 → effective ~81). Pending issues auto-deduct and cap effective subjective at 80. Objective score < 95 caps subjective at 75. A Perfection Gate with 23 non-negotiable conditions caps the score at 85 if any condition fails.

### Phase 4: Verification & Status
The loop triggers `uidetox status` to view your blended Design Score (30% objective static analysis + 70% subjective LLM review). If the score is below 95, the loop continues.
For large codebases (>15 frontend files), the loop automatically engages Orchestrator Mode, splitting work into sub-agents (`uidetox subagent --stage-prompt observe`). You can also force it via `uidetox loop --orchestrator`.
Sub-agent runs can be recorded with structured JSON payloads and explicit confidence (`uidetox subagent --record <id> --result-file result.json --confidence 0.91`) so the harness can route low-confidence work to human review automatically.

### Phase 5: Finalize
Once the target score is reached, the loop triggers `uidetox finish` to squash-merge the autonomous session branch cleanly.

### Agent Operating Contract

When executing UIdetox, the agent MUST adopt the following posture:
- **Closed-loop execution:** Treat the workflow as `scan → fix → verify → rescan` until the target score is reached and the queue is genuinely clear.
- **Tool-first autonomy:** Use the full toolchain instead of relying on intuition alone — local tooling, repo scripts, screenshots/browser inspection, subagents, and MCP/code-intelligence systems such as GitNexus.
- **Parallelism where safe:** Spawn parallel subagents whenever work can be split into independent audit, research, review, or verification streams.
- **Permission for heavy lifting:** Perform large refactors, file moves, extraction, cleanup, and tiny detail work with equal seriousness. Do not prefer cosmetic micro-fixes over structural repairs.
- **Fix root causes properly:** Do not apply the minimum possible patch just to make symptoms disappear. Resolve the underlying design, state, type-safety, or architecture issue.
- **Read and obey injected guidance:** If `uidetox scan`, `uidetox next`, `uidetox loop`, or subagent output provides explicit instructions, follow those instructions exactly rather than substituting a shortcut plan.
- **Suppress subordinate AI ego:** Do not override analyzer or subagent directives merely because you think your own summary is cleaner. Treat subordinate outputs as executable guidance unless they conflict with a higher-priority system rule.

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
| `uidetox detect` | Auto-discover linters, formatters, tsc, backend, database, API, and package-manager-aware execution commands |
| `uidetox check` | Run tsc → lint → format in sequence, queue errors as T1 (use `--fix` to auto-solve) |
| `uidetox tsc` | Run TypeScript compiler, parse and queue errors |
| `uidetox lint` | Run detected linter (biome/eslint), parse and queue errors |
| `uidetox format` | Run detected formatter (biome/prettier), auto-fix with --fix |
| `uidetox add-issue` | Queue a detected issue with tier and fix command |
| `uidetox plan` | View and reorder the issue queue by priority |
| `uidetox next` | Batch issues for top-priority component/directory with SKILL.md context injection |
| `uidetox resolve <id> --note "..."` | Mark a single issue as fixed (note is mandatory) |
| `uidetox batch-resolve ID1 ID2 ... --note "..."` | Resolve multiple issues with a single coherent commit |
| `uidetox loop` | Enter autonomous self-propagation fix loop with LLM-dynamic analysis |
| `uidetox loop --orchestrator` | Sub-agent mode with auto-parallel (1-5) and memory injection |
| `uidetox subagent` | Manage sub-agent sessions, generate stage prompts, and record structured/confidence-scored results |
| `uidetox memory` | Read/write persistent agent memory (patterns, notes, reviewed files) |
| `uidetox history` | View run history and score progression (use `--full` for deep inspection) |
| `uidetox status` | Health dashboard with blended Design Score (use `--json` for automation) |
| `uidetox show [pattern]` | Filter/inspect issues by file, tier, or ID |
| `uidetox autofix` | Batch all safe T1 fixes for the agent to apply (use `--dry-run` to preview only) |
| `uidetox rescan` | Clear queue, run 50-rule static analyzer, re-audit from scratch |
| `uidetox finish` | Squash merges the autonomous session branch cleanly |
| `uidetox exclude <path>` | Skip a directory during scanning |
| `uidetox review` | LLM subjective UX quality review (use `--score N` to record assessment) |
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
uidetox update-skill cursor     # → .cursor/skills/uidetox/ + .cursor/rules/ + .cursor/agents/
uidetox update-skill gemini     # → .gemini/skills/uidetox/ + GEMINI.md (section-injected)
uidetox update-skill codex      # → ~/.codex/skills/uidetox/ + ~/.codex/prompts/
uidetox update-skill windsurf   # → .windsurf/skills/uidetox/ + .windsurfrules (section-injected)
uidetox update-skill copilot    # → .github/skills/uidetox/ + .github/copilot-instructions.md (section-injected)
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
│   ├── analyzer.py               # 50-rule static slop detector (deterministic anti-pattern scan)
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

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **UIdetox** (873 symbols, 2501 relationships, 66 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/UIdetox/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/UIdetox/context` | Codebase overview, check index freshness |
| `gitnexus://repo/UIdetox/clusters` | All functional areas |
| `gitnexus://repo/UIdetox/processes` | All execution flows |
| `gitnexus://repo/UIdetox/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

- Re-index: `npx gitnexus analyze`
- Check freshness: `npx gitnexus status`
- Generate docs: `npx gitnexus wiki`

<!-- gitnexus:end -->
