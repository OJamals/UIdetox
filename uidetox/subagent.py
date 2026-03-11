"""Sub-agent session management: create, track, and record sub-agent work."""

import json
import os
import uuid
from pathlib import Path

from uidetox.analyzer import IGNORE_DIRS # type: ignore
from uidetox.state import get_uidetox_dir, ensure_uidetox_dir, load_state, load_config # type: ignore
from uidetox.utils import now_iso # type: ignore


STAGES = ["observe", "diagnose", "prioritize", "fix", "verify"]


def _sessions_dir() -> Path:
    d = get_uidetox_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_iso() -> str:
    return now_iso()


def _session_id() -> str:
    return str(uuid.uuid4()).split("-")[0]


def create_session(stage: str, prompt: str) -> str:
    """Create a new sub-agent session with a generated prompt.

    Args:
        stage: One of the 5 stages (observe, diagnose, prioritize, fix, verify).
        prompt: The full prompt text for the sub-agent.

    Returns:
        The session ID.
    """
    session_id = _session_id()
    session_dir = _sessions_dir() / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write prompt
    with open(session_dir / "prompt.md", "w", encoding="utf-8") as f:
        f.write(prompt)

    # Write metadata
    meta = {
        "session_id": session_id,
        "stage": stage,
        "status": "pending",
        "created_at": _now_iso(),
        "completed_at": None,
    }
    with open(session_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return session_id


def record_result(session_id: str, result: dict) -> bool:
    """Record the result of a sub-agent session.

    Args:
        session_id: The session to update.
        result: Dict with the sub-agent's findings (issues found, files changed, etc).

    Returns:
        True if recorded, False if session not found.
    """
    session_dir = _sessions_dir() / f"session_{session_id}"
    if not session_dir.exists():
        return False

    # Write result
    with open(session_dir / "result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Update meta
    meta_path = session_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    
    # Parse confidence score if provided
    confidence = 1.0
    text = result.get("note", "")
    import re
    m = re.search(r'CONFIDENCE:\s*(0\.\d+|1\.0)', text, re.IGNORECASE)
    if m:
        confidence = float(m.group(1))

    meta["status"] = "completed_with_warnings" if confidence < 0.85 else "completed"
    meta["confidence"] = confidence
    meta["completed_at"] = _now_iso()
    
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return True


def list_sessions() -> list[dict]:
    """Return all sessions with their metadata."""
    sessions_dir = _sessions_dir()
    results = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        meta_path = session_dir / "meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                results.append(meta)
            except (json.JSONDecodeError, OSError):
                continue
    return results


def get_session(session_id: str) -> dict | None:
    """Get full session details including prompt and result."""
    session_dir = _sessions_dir() / f"session_{session_id}"
    if not session_dir.exists():
        return None

    meta_path = session_dir / "meta.json"
    prompt_path = session_dir / "prompt.md"
    result_path = session_dir / "result.json"

    result = {}
    if meta_path.exists():
        result["meta"] = json.loads(meta_path.read_text())
    if prompt_path.exists():
        result["prompt"] = prompt_path.read_text()
    if result_path.exists():
        result["result"] = json.loads(result_path.read_text())
    return result


def get_frontend_files() -> list[str]:
    frontend_exts = {".tsx", ".jsx", ".html", ".css", ".scss", ".vue", ".svelte", ".ts", ".js"}
    files = []
    
    for dirpath, dirnames, filenames in os.walk("."):
        new_dir = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith('.')]
        dirnames.clear()
        dirnames.extend(new_dir)
        for filename in filenames:
            if Path(filename).suffix.lower() in frontend_exts:
                files.append(os.path.join(dirpath, filename))
    return sorted(files)


def _build_memory_block(query: str = "") -> str:
    """Build a memory injection block from persistent agent memory.

    Injects learned patterns, notes, and session context so sub-agents
    have continuity with prior work. If a query is provided, performs
    a semantic search using ChromaDB.
    """
    try:
        from uidetox.memory import get_patterns, get_notes, get_session as get_mem_session, get_last_scan
    except ImportError:
        return ""

    sections: list[str] = []

    patterns = get_patterns(query=query)
    if patterns:
        lines = ["## Learned Patterns (from prior sessions — MUST follow)"]
        for p in patterns[-15:]:  # Last 15 to keep prompt size manageable
            lines.append(f"- [{p.get('category', 'general')}] {p['pattern']}")
        sections.append("\n".join(lines))

    notes = get_notes(query=query)
    if notes:
        lines = ["## Agent Notes (persistent context)"]
        for n in notes[-10:]:
            lines.append(f"- {n['note']}")
        sections.append("\n".join(lines))

    session = get_mem_session()
    if session:
        lines = ["## Session Continuity"]
        lines.append(f"- Last Phase: {session.get('phase', 'unknown')}")
        lines.append(f"- Last Command: {session.get('last_command', 'none')}")
        if session.get("last_component"):
            lines.append(f"- Last Component: {session['last_component']}")
        lines.append(f"- Issues Fixed This Session: {session.get('issues_fixed_this_session', 0)}")
        if session.get("context"):
            lines.append(f"- Context: {session['context']}")
        sections.append("\n".join(lines))

    last_scan = get_last_scan()
    if last_scan:
        lines = ["## Last Scan Summary"]
        lines.append(f"- Total Found: {last_scan.get('total_found', 0)}")
        by_tier = last_scan.get("by_tier", {})
        if by_tier:
            tier_str = ", ".join(f"{k}: {v}" for k, v in sorted(by_tier.items()))
            lines.append(f"- By Tier: {tier_str}")
        top = last_scan.get("top_files", [])
        if top:
            lines.append(f"- Hottest Files: {', '.join(top[:5])}")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    return "\n\n".join(["# Memory Bank Injection"] + sections) + "\n"


def _build_deconfliction_block(shard_index: int, total_shards: int, shard_files: list[str]) -> str:
    """Build a deconfliction directive for parallel sub-agents.

    Prevents merge conflicts by ensuring each shard only touches its assigned files.
    """
    if total_shards <= 1:
        return ""

    return f"""## Shard Deconfliction (CRITICAL — violating this causes merge conflicts)
- You are shard {shard_index + 1} of {total_shards}.
- You may ONLY read and modify files in YOUR shard assignment below.
- Do NOT touch ANY file outside your shard, even if you see issues in it.
- If you discover issues in files outside your shard, note them but DO NOT fix.
- Your assigned files:
{chr(10).join(f'  - {f}' for f in shard_files)}
"""


def generate_stage_prompt(stage: str, parallel: int = 1) -> list[str]:
    """Generate focused prompts for a specific sub-agent stage.

    If parallel > 1, chunks files or issues into non-overlapping buckets
    for massive AI swarm parallel execution.
    """
    state = load_state()
    config = load_config()
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])
    tooling = config.get("tooling", {})

    # Design dials — shared across all stage prompts
    variance = config.get("DESIGN_VARIANCE", 8)
    intensity = config.get("MOTION_INTENSITY", 6)
    density = config.get("VISUAL_DENSITY", 4)
    dials_block = f"""## Active Design Dials
- DESIGN_VARIANCE  = {variance}  {'(asymmetric, masonry, massive whitespace)' if variance > 7 else '(varied sizes, offset margins)' if variance > 4 else '(clean, centered, standard grids)'}
- MOTION_INTENSITY = {intensity}  {'(scroll-triggered, spring physics, magnetic)' if intensity > 7 else '(fade-ins, transitions, staggered entry)' if intensity > 5 else '(CSS hover/active only)'}
- VISUAL_DENSITY   = {density}  {'(cockpit mode, dense data)' if density > 7 else '(standard web app spacing)' if density > 3 else '(art gallery, spacious, luxury)'}

Use these dials to calibrate your decisions. Higher variance = more asymmetry required."""

    if stage == "observe":
        memory_block = _build_memory_block()
        if parallel > 1:
            files = get_frontend_files()
            if not files:
                return [_observe_prompt(tooling, [], dials_block, memory_block, 0, 1)]
            chunk_size = max(1, len(files) // parallel)
            chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)] # type: ignore
            # Merge trailing chunk if rounding caused an extra bucket
            if len(chunks) > parallel:
                chunks[parallel-1].extend(chunks.pop()) # type: ignore
            return [
                _observe_prompt(tooling, chunk, dials_block, memory_block, idx, len(chunks))
                for idx, chunk in enumerate(chunks)
            ]
        return [_observe_prompt(tooling, [], dials_block, memory_block, 0, 1)]

    elif stage == "diagnose":
        return [_diagnose_prompt(issues, dials_block)]

    elif stage == "prioritize":
        return [_prioritize_prompt(issues)]

    elif stage == "fix":
        if not issues:
            return [_fix_prompt([], dials_block, 0, 1)]

        tiers_order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
        # Safely group by file to prevent merge conflicts
        grouped = {}
        for issue in issues:
            f = issue.get("file")
            if f not in grouped:
                grouped[f] = []
            grouped[f].append(issue)

        sorted_groups = sorted(
            grouped.values(),
            key=lambda group: min(tiers_order.get(i.get("tier", "T4"), 5) for i in group)
        )

        # Take the most pressing file-groups to batch, up to parallel * 3
        top_groups = sorted_groups[:parallel * 3] # type: ignore

        # Distribute file-groups into parallel buckets
        buckets = [[] for _ in range(parallel)]
        for i, group in enumerate(top_groups):
            buckets[i % parallel].extend(group)

        # Strip empty buckets if there were fewer files than agents
        buckets = [b for b in buckets if b]

        if not buckets:  # Fallback sanity check
            buckets = [issues[:5]] # type: ignore

        total_buckets = len(buckets)
        return [_fix_prompt(bucket, dials_block, idx, total_buckets) for idx, bucket in enumerate(buckets)]

    elif stage == "verify":
        return [_verify_prompt(issues, resolved)]

    return [f"Unknown stage: {stage}"]


def _observe_prompt(tooling: dict, files: list[str], dials_block: str,
                    memory_block: str = "", shard_index: int = 0, total_shards: int = 1) -> str:
    # Build file target list if specific shard provided
    target_directive = "Systematically scan the codebase and catalog everything you see."
    deconfliction = ""
    if files:
        file_list = "\n".join(f"- {f}" for f in files)
        target_directive = f"Systematically scan ONLY the following files in your shard:\n{file_list}"
        deconfliction = _build_deconfliction_block(shard_index, total_shards, files)

    return f"""# UIdetox Sub-Agent: OBSERVE Stage

{memory_block}
{dials_block}
{deconfliction}

## Your Mission
{target_directive} DO NOT fix anything yet.

## Tools Available
Use GitNexus to map codebase flows before deep diving!
- `npx gitnexus analyze --embeddings` (or `npx gitnexus analyze` if embeddings are not needed)
- npx gitnexus query <concept>

## What to Catalog
For every frontend file, note:
- **Typography**: Font families, sizes, weights, line heights, tracking
- **Colors**: All color values (hex, rgb, hsl, oklch, named, CSS variables, Tailwind classes)
- **Layout**: Grid systems, flex patterns, max-widths, padding/margin patterns, symmetry vs asymmetry
- **Components**: UI patterns used (cards, modals, heroes, navbars, forms, accordions, pricing tables)
- **Motion**: Animations, transitions, hover/focus/active effects, easing curves
- **States**: Loading, error, empty, disabled state handling
- **Accessibility**: ARIA labels, focus indicators, skip-to-content, lang attributes
- **Content**: Placeholder data quality (names, numbers, dates, copy tone)

## Output Format
For each file, output a structured observation:
```
FILE: <path>
TYPOGRAPHY: <what fonts/sizes you see>
COLORS: <what color values you see>
LAYOUT: <what layout patterns you see>
COMPONENTS: <what UI components you see>
MOTION: <what animations/transitions you see>
STATES: <what state handling you see>
ACCESSIBILITY: <what a11y features are present or missing>
CONTENT: <quality of placeholder data and copy>
```

## Rules
- Be exhaustive. Miss nothing.
- Don't evaluate. Just observe and record.
- Include inline styles, CSS files, styled-components, Tailwind classes — everything.
"""


def _diagnose_prompt(issues: list, dials_block: str) -> str:
    existing = "\n".join(
        f"- [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in issues[:20] # type: ignore
    ) if issues else "None yet."

    return f"""# UIdetox Sub-Agent: DIAGNOSE Stage

{dials_block}

## Your Mission
Compare the observations from the OBSERVE stage against SKILL.md rules.
Identify every AI slop pattern and design violation.

## Already Known Issues
{existing}

## Systematic Audit Checklist (check ALL categories)

### 1. Typography (consult reference/typography.md)
- Banned fonts: Inter, Roboto, Arial, Open Sans, system-ui as primary
- Missing type hierarchy (only Regular 400 and Bold 700 used)
- Serif fonts on dashboards
- Monospace as lazy "developer" vibe
- Large icons above every heading
- Hardcoded px font sizes instead of rem (accessibility)
- Overly tight leading/line-height on body paragraphs

### 2. Color & Contrast (consult reference/color-and-contrast.md)
- Purple-blue gradients (the #1 AI fingerprint)
- Cyan-on-dark palette
- Pure black (#000000)
- Gray text on colored backgrounds
- Gradient text on headings
- Oversaturated accents (> 80%)
- Neon/outer glows
- No dark mode support
- Raw CSS named colors (red, blue, green) instead of palette

### 3. Layout & Spacing (consult reference/spatial-design.md)
- Centered hero sections (banned when DESIGN_VARIANCE > 4)
- 3-column card feature rows
- h-screen instead of min-h-[100dvh]
- No max-width container
- Cards for everything / nested cards
- Uniform spacing everywhere
- Overpadded layouts
- Custom flex centering instead of grid place-items-center

### 4. Materiality & Surfaces
- Glassmorphism (backdrop-blur + transparency)
- Oversized border-radius (20-32px on everything)
- Oversized shadows (2xl/3xl)
- Pill-shaped badges
- Solid opaque borders for dividers (missing /50 opacity)

### 5. Motion & Interaction (consult reference/motion-design.md)
- Bounce/elastic easing
- animate-bounce/pulse/spin
- Missing hover, focus, active states
- Transform animations on nav links
- Hover states missing transition-all/colors

### 6. States & UX Completeness
- Missing loading states (or generic spinners instead of skeletons)
- Missing error states
- Missing empty states
- Missing disabled states
- Native browser scrollbars (missing custom styling/hiding)

### 7. Content & Data Quality
- Lorem Ipsum
- Generic names (John Doe, Jane Smith, Acme Corp)
- AI copy cliches (Elevate, Seamless, Unleash, Next-Gen)
- Round placeholder numbers (99.99%, 50%)
- Broken Unsplash links
- Emojis in UI

### 8. Code Quality & Semantics
- Div soup (no semantic HTML)
- Arbitrary z-index (9999)
- Inline styles mixed with classes
- Import hallucinations

### 9. Accessibility
- Missing focus indicators
- No ARIA labels on icon-only buttons
- Insufficient contrast ratios
- No skip-to-content link
- Labels missing htmlFor attributes linking to inputs

### 10. Strategic Omissions
- Missing 404 page
- Missing legal links
- Missing form validation
- Missing favicon
- Missing meta tags

## Output Format
For each issue found, output:
```
ISSUE: <description>
FILE: <path>
TIER: <T1|T2|T3|T4>
FIX: <what command or action to take>
```

Then run:
```
uidetox add-issue --file <path> --tier <tier> --issue "<description>" --fix-command "<cmd>"
```
"""


def _prioritize_prompt(issues: list) -> str:
    issue_list = "\n".join(
        f"- [{i.get('id')}] [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in issues
    ) if issues else "No issues in queue."

    return f"""# UIdetox Sub-Agent: PRIORITIZE Stage

## Your Mission
Review all queued issues and optimize the fix order for maximum impact with minimum risk.

## Current Queue
{issue_list}

## Prioritization Rules (from AGENTS.md)
1. Font swap — biggest instant improvement, lowest risk
2. Color palette cleanup — remove clashing or oversaturated colors
3. Hover and active states — makes the interface feel alive
4. Layout and spacing — proper grid, max-width, consistent padding
5. Replace generic components — swap cliché patterns for modern alternatives
6. Add loading, empty, and error states — makes it feel finished
7. Polish typography scale and spacing — the premium final touch

## Output
Provide the recommended fix order as a numbered list with rationale for each grouping.
"""


def _fix_prompt(batch: list, dials_block: str,
                shard_index: int = 0, total_shards: int = 1) -> str:
    if not batch:
        return "# No issues to fix. Run `uidetox scan` first."

    batch_text = "\n".join(
        f"- [{i.get('id')}] [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in batch
    )

    # Build inline context for the fix batch (same pattern as next.py)
    from uidetox.commands.next import SKILL_CONTEXT, _get_relevant_context # type: ignore
    contexts = _get_relevant_context(batch)
    context_block = ""
    if contexts:
        lines = ["## Relevant SKILL.md Design Rules"]
        for ctx, ref_file in contexts:
            lines.append(f"- {ctx}")
            if ref_file:
                lines.append(f"  (Deep-dive: {ref_file})")
        context_block = "\n".join(lines)

    # Build memory and deconfliction blocks
    memory_block = _build_memory_block(query=batch_text)
    batch_files = list(set(i.get("file", "") for i in batch))
    deconfliction = _build_deconfliction_block(shard_index, total_shards, batch_files)

    return f"""# UIdetox Sub-Agent: FIX Stage

{memory_block}
{dials_block}
{deconfliction}

## Your Mission
Fix the following {len(batch)} issues. Apply changes directly to the codebase.

## Issues to Fix
{batch_text}

{context_block}

## Tools & Rules
- Use `npx gitnexus impact <symbol>` before refactoring any exports
- Follow SKILL.md design rules for every change
- Fix ALL issues in one pass per component, then batch-resolve:
  `uidetox batch-resolve <ID1> <ID2> ... --note "what you changed"`
- Run `uidetox check --fix` BEFORE batch-resolve to catch regressions
- Move to the next component immediately after resolving
"""


def _verify_prompt(issues: list, resolved: list) -> str:
    return f"""# UIdetox Sub-Agent: VERIFY Stage

## Your Mission
Re-scan the codebase to confirm improvements. Check that fixes actually improved the interface.

## Current State
- Pending issues: {len(issues)}
- Previously resolved: {len(resolved)}

## Verification Checklist
1. Run `uidetox status` to check the current Design Score
2. Re-read every file that was modified during the FIX stage
3. Confirm the fixes match SKILL.md rules
4. Check for cascade effects (fixing one thing may reveal or create new issues)
5. If new issues are found, queue them: `uidetox add-issue --file <path> --tier <tier> --issue "<desc>" --fix-command "<cmd>"`
6. Run `uidetox status` again to see the updated score

## Output
Report the verification results:
- Score before and after
- Any new issues discovered
- Overall assessment: is the interface clean of AI slop?
- Yield a final CONFIDENCE: <0.0 - 1.0> score based on your certainty regarding the fixes.
"""
