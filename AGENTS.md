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
The loop triggers `uidetox scan` on the project. The scan auto-detects tooling (TypeScript, biome/eslint/prettier, backend frameworks, database ORMs, API layers) and performs:
- **Static Slop Analysis:** A 218-rule deterministic analyzer scans all frontend files for known AI anti-patterns (glassmorphism, purple-blue gradients, bounce animations, oversized shadows, gray-on-color text, missing dark mode, etc.).
- **Design Audit:** The agent reads frontend files and evaluates against SKILL.md.
- **Full-Stack Integration:** If backend/database/API layers are detected, the agent checks for DTO mismatches, schema misalignment, missing error states, and type safety gaps across boundaries. **CRITICAL:** When generating or fixing code, the agent MUST enforce strict type safety and conform perfectly to existing backend architectures, API contracts, and database DTOs.

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
Run `uidetox review` to perform an LLM-driven subjective quality assessment across 4 dimensions (Consistency, Cohesion, Craft, Identity), then `uidetox review --score <N>` to record it.

### Phase 4: Verification & Status
The loop triggers `uidetox status` to view your blended Design Score (60% objective static analysis + 40% subjective LLM review). If the score is below 95, the loop continues.
For large codebases (>15 frontend files), the loop automatically engages Orchestrator Mode, splitting work into sub-agents (`uidetox subagent --stage-prompt observe`). You can also force it via `uidetox loop --orchestrator`.

### Phase 5: Finalize
Once the target score is reached, the loop triggers `uidetox finish` to squash-merge the autonomous session branch cleanly.

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
| `uidetox setup` | Initialize project config and design dials (`--design-variance`, `--motion-intensity`, `--visual-density`, `--dev-server`, `--auto-commit`, `--no-auto-commit`) |
| `uidetox scan` | Full audit: auto-detect tooling → static analyzer → design review |
| `uidetox detect` | Auto-discover linters, formatters, tsc, backend, database, API |
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
| `uidetox subagent` | Manage sub-agent sessions and generate stage prompts |
| `uidetox memory` | Read/write persistent agent memory (patterns, notes, reviewed files) |
| `uidetox history` | View run history and score progression (use `--full` for deep inspection) |
| `uidetox status` | Health dashboard with blended Design Score (use `--json` for automation) |
| `uidetox show [pattern]` | Filter/inspect issues by file, tier, or ID |
| `uidetox autofix` | Batch all safe T1 fixes for the agent to apply (use `--dry-run` to preview only) |
| `uidetox capture` | Capture before/after screenshots + visual diff via Playwright (`--stage before/after`, `--url`, `--responsive`). **Start your dev server first** — uidetox does not launch it. Diff is amplified 8× for visibility. |
| `uidetox diff` | Compare fresh static analysis against stored baseline (NEW / FIXED / UNCHANGED). Supports `--since <sha>`, `--output table/json/github`, `--save`. |
| `uidetox watch` | Poll directory for file changes and re-scan on modification (`--path`, `--interval`, `--no-clear`). |
| `uidetox rescan` | Clear queue, run 218-rule static analyzer, re-audit from scratch |
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

**`dev_server`** (string URL) — Optional capture target used by `uidetox capture`.
- Defaults to `http://localhost:3000`
- Override it per invocation with `--url`
- Persist it in `.uidetox/config.json` when your app runs on a different port (e.g. Vite on `http://localhost:5173`)

Default baseline: `(8, 6, 4)`. Override via `uidetox setup --design-variance N --motion-intensity N --visual-density N --dev-server URL` or direct instruction.

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
│   ├── cli.py                    # Argparse router (36 commands, dynamic slash-command loading)
│   ├── state.py                  # Issue queue + config in .uidetox/
│   ├── tooling.py                # Auto-detection (tsc, biome, eslint, NestJS, etc.)
│   ├── analyzer.py               # 218-rule static slop detector (deterministic anti-pattern scan)
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

This project is indexed by GitNexus as **UIdetox** (3610 symbols, 4863 relationships, 164 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale or fails because `.gitnexus/lbug` is missing, refresh the local index first. Prefer:
> `pnpm --allow-build=@ladybugdb/core --allow-build=tree-sitter --allow-build=tree-sitter-c --allow-build=tree-sitter-c-sharp --allow-build=tree-sitter-cpp --allow-build=tree-sitter-dart --allow-build=tree-sitter-go --allow-build=tree-sitter-java --allow-build=tree-sitter-javascript --allow-build=tree-sitter-kotlin --allow-build=tree-sitter-php --allow-build=tree-sitter-python --allow-build=tree-sitter-ruby --allow-build=tree-sitter-rust --allow-build=tree-sitter-swift --allow-build=tree-sitter-typescript --allow-build=tree-sitter-cli dlx gitnexus analyze`
> Add `--embeddings` if `.gitnexus/meta.json` reports embeddings > 0. If `pnpm` is unavailable, fall back to `npx gitnexus analyze`.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/UIdetox/context` | Codebase overview, check index freshness |
| `gitnexus://repo/UIdetox/clusters` | All functional areas |
| `gitnexus://repo/UIdetox/processes` | All execution flows |
| `gitnexus://repo/UIdetox/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

### Local refresh commands

- Re-index: `pnpm --allow-build=@ladybugdb/core --allow-build=tree-sitter --allow-build=tree-sitter-c --allow-build=tree-sitter-c-sharp --allow-build=tree-sitter-cpp --allow-build=tree-sitter-dart --allow-build=tree-sitter-go --allow-build=tree-sitter-java --allow-build=tree-sitter-javascript --allow-build=tree-sitter-kotlin --allow-build=tree-sitter-php --allow-build=tree-sitter-python --allow-build=tree-sitter-ruby --allow-build=tree-sitter-rust --allow-build=tree-sitter-swift --allow-build=tree-sitter-typescript --allow-build=tree-sitter-cli dlx gitnexus analyze`
- Re-index with embeddings: `pnpm --allow-build=@ladybugdb/core --allow-build=tree-sitter --allow-build=tree-sitter-c --allow-build=tree-sitter-c-sharp --allow-build=tree-sitter-cpp --allow-build=tree-sitter-dart --allow-build=tree-sitter-go --allow-build=tree-sitter-java --allow-build=tree-sitter-javascript --allow-build=tree-sitter-kotlin --allow-build=tree-sitter-php --allow-build=tree-sitter-python --allow-build=tree-sitter-ruby --allow-build=tree-sitter-rust --allow-build=tree-sitter-swift --allow-build=tree-sitter-typescript --allow-build=tree-sitter-cli dlx gitnexus analyze --embeddings`
- Fallback when `pnpm` is unavailable: `npx gitnexus analyze`

<!-- gitnexus:end -->
