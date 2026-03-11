"""Sub-agent session management: create, track, and record sub-agent work."""

import json
import os
import uuid
from pathlib import Path

from uidetox.analyzer import IGNORE_DIRS
from uidetox.state import get_uidetox_dir, ensure_uidetox_dir, load_state, load_config
from uidetox.utils import now_iso


STAGES = ["observe", "diagnose", "prioritize", "fix", "verify"]


def _sessions_dir() -> Path:
    d = get_uidetox_dir() / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_iso() -> str:
    return now_iso()


def _session_id() -> str:
    return str(uuid.uuid4())[:8]


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
    meta["status"] = "completed"
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
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith('.')]
        for filename in filenames:
            if Path(filename).suffix.lower() in frontend_exts:
                files.append(os.path.join(dirpath, filename))
    return sorted(files)


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

    if stage == "observe":
        if parallel > 1:
            files = get_frontend_files()
            if not files:
                return [_observe_prompt(tooling, [])]
            chunk_size = max(1, len(files) // parallel)
            chunks = [files[i:i + chunk_size] for i in range(0, len(files), chunk_size)]
            # Merge trailing chunk if rounding caused an extra bucket
            if len(chunks) > parallel:
                chunks[parallel-1].extend(chunks.pop())
            return [_observe_prompt(tooling, chunk) for chunk in chunks]
        return [_observe_prompt(tooling, [])]

    elif stage == "diagnose":
        return [_diagnose_prompt(issues)]

    elif stage == "prioritize":
        return [_prioritize_prompt(issues)]

    elif stage == "fix":
        if not issues:
            return [_fix_prompt([])]
            
        tiers_order = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
        # Safely group by file to prevent merge conflicts
        grouped = {}
        for issue in issues:
            grouped.setdefault(issue.get("file"), []).append(issue)
            
        sorted_groups = sorted(
            grouped.values(), 
            key=lambda group: min(tiers_order.get(i.get("tier", "T4"), 5) for i in group)
        )
        
        # Take the most pressing file-groups to batch, up to parallel * 3
        top_groups = sorted_groups[:parallel * 3]
        
        # Distribute file-groups into parallel buckets
        buckets = [[] for _ in range(parallel)]
        for i, group in enumerate(top_groups):
            buckets[i % parallel].extend(group)
            
        # Strip empty buckets if there were fewer files than agents
        buckets = [b for b in buckets if b]
        
        if not buckets: # Fallback sanity check
            buckets = [issues[:5]]
            
        return [_fix_prompt(bucket) for bucket in buckets]

    elif stage == "verify":
        return [_verify_prompt(issues, resolved)]

    return [f"Unknown stage: {stage}"]


def _observe_prompt(tooling: dict, files: list[str]) -> str:
    # Build file target list if specific shard provided
    target_directive = "Systematically scan the codebase and catalog everything you see."
    if files:
        file_list = "\n".join(f"- {f}" for f in files)
        target_directive = f"Systematically scan ONLY the following files in your shard:\n{file_list}"

    return f"""# UIdetox Sub-Agent: OBSERVE Stage

## Your Mission
{target_directive} DO NOT fix anything yet.

## What to Catalog
For every frontend file, note:
- **Typography**: Font families, sizes, weights, line heights
- **Colors**: All color values (hex, rgb, hsl, named, CSS variables)
- **Layout**: Grid systems, flex patterns, max-widths, padding/margin patterns
- **Components**: UI patterns used (cards, modals, heroes, navbars, forms)
- **Motion**: Animations, transitions, hover effects
- **States**: Loading, error, empty, disabled state handling

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
```

## Rules
- Be exhaustive. Miss nothing.
- Don't evaluate. Just observe and record.
- Include inline styles, CSS files, styled-components, Tailwind classes — everything.
"""


def _diagnose_prompt(issues: list) -> str:
    existing = "\n".join(
        f"- [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in issues[:20]
    ) if issues else "None yet."

    return f"""# UIdetox Sub-Agent: DIAGNOSE Stage

## Your Mission
Compare the observations from the OBSERVE stage against SKILL.md rules.
Identify every AI slop pattern and design violation.

## Already Known Issues
{existing}

## What to Check (from SKILL.md)
1. **AI Slop Fingerprints**: Inter font, purple-blue gradients, glassmorphism, card grids, hero metrics, bounce animations
2. **Typography**: System defaults, single font, no scale hierarchy
3. **Color**: Generic palettes, insufficient contrast, no dark mode consideration
4. **Layout**: Centered single-column only, no max-width, inconsistent spacing
5. **States**: Missing loading/error/empty/disabled states
6. **Motion**: No hover effects, no transitions, or gratuitous bounce animations
7. **Accessibility**: Missing ARIA labels, poor focus indicators, insufficient contrast

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


def _fix_prompt(batch: list) -> str:
    if not batch:
        return "# No issues to fix. Run `uidetox scan` first."

    batch_text = "\n".join(
        f"- [{i.get('id')}] [{i.get('tier')}] {i.get('file')}: {i.get('issue')}" for i in batch
    )

    return f"""# UIdetox Sub-Agent: FIX Stage

## Your Mission
Fix the following {len(batch)} issues. Apply changes directly to the codebase.

## Issues to Fix
{batch_text}

## Rules
- Follow SKILL.md design rules for every change
- After fixing each issue, run: `uidetox resolve <ISSUE_ID> --note "what you changed"`
- After resolving a batch, run: `uidetox check --fix` to catch regressions
- Verify your fix doesn't break anything
- Move to the next issue immediately after resolving
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
"""
