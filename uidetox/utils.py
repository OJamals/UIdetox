"""Shared utilities for UIdetox."""

import shlex
import subprocess
from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def now_iso_filename() -> str:
    """Return the current UTC time formatted for use in filenames (no colons)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def safe_split_cmd(cmd: str) -> list[str]:
    """Split a shell command string safely, handling paths with spaces.

    Falls back to simple split if shlex parsing fails (e.g. Windows paths).
    """
    try:
        return shlex.split(cmd)
    except ValueError:
        return cmd.split()


def run_tool(
    cmd: str,
    *,
    cwd: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run an external tool command with standard error handling.

    Wraps ``subprocess.run(safe_split_cmd(cmd), ...)`` with the boilerplate
    options used throughout the codebase: capture_output, text mode, cwd,
    and timeout.

    Returns:
        The :class:`subprocess.CompletedProcess` result.

    Raises:
        FileNotFoundError: When the command binary is missing.
        subprocess.TimeoutExpired: When execution exceeds *timeout*.
    """
    return subprocess.run(
        safe_split_cmd(cmd),
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=timeout,
    )


def compute_design_score(state: dict) -> dict:
    """Compute the blended design score from state.

    Returns a dict with:
      - objective_score: int (0-100) from static analysis slop ratio
      - subjective_score: int | None from LLM review
      - blended_score: int (0-100) final blended score
      - current_slop: weighted slop points remaining
      - resolved_slop: weighted slop points resolved
      - total_slop: total weighted slop points
    """
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])
    stats = state.get("stats", {})
    scans_run = stats.get("scans_run", 0)

    # Higher tiers = more critical → heavier penalty on the score
    tier_weights = {"T1": 10, "T2": 5, "T3": 3, "T4": 1}

    current_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in issues)
    resolved_slop = sum(tier_weights.get(i.get("tier", "T4"), 10) for i in resolved)
    total_slop = current_slop + resolved_slop

    if scans_run == 0 and total_slop == 0:
        # No scan has been run yet — return None to distinguish from a real score.
        # Callers should handle None (e.g. display "—" or "Not scanned yet").
        objective_score = None  # type: ignore[assignment]
    elif total_slop == 0:
        objective_score = 100
    else:
        objective_score = int(100 - ((current_slop / total_slop) * 100))
        objective_score = max(0, min(100, objective_score))

    subjective_score = state.get("subjective", {}).get("score")

    if objective_score is None:
        blended = subjective_score if subjective_score is not None else 0
    elif subjective_score is not None:
        blended = int(objective_score * 0.3 + subjective_score * 0.7)
    else:
        blended = objective_score

    return {
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "blended_score": blended,
        "current_slop": current_slop,
        "resolved_slop": resolved_slop,
        "total_slop": total_slop,
    }


# ── Canonical category inference (used by scan, autofix, plan, status) ──

ISSUE_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "typography": [
        "font", "typography", "inter", "roboto", "type scale", "line-height",
        "px font", "letter-spacing", "kerning",
    ],
    "color": [
        "color", "gradient", "palette", "contrast", "dark mode", "purple",
        "blue", "black", "hex color", "named css color",
    ],
    "layout": [
        "layout", "grid", "spacing", "padding", "margin", "dashboard",
        "card", "center", "flex center", "viewport", "h-screen", "overpadded",
    ],
    "motion": [
        "animation", "bounce", "pulse", "spin", "transition", "motion",
    ],
    "materiality": [
        "shadow", "glassmorphism", "radius", "border", "backdrop", "blur",
        "glow", "opacity", "neon", "gradient text",
    ],
    "states": [
        "loading", "error", "empty", "skeleton", "disabled", "hover",
        "focus", "cursor-not-allowed", "missing hover", "missing focus",
    ],
    "content": [
        "copy", "lorem", "generic", "placeholder", "cliche", "john doe",
        "acme", "emoji", "oops", "exclamation", "unsplash",
    ],
    "code quality": [
        "div soup", "semantic", "z-index", "inline style", "!important",
        "ternary", "magic number", "any type", "ts-ignore", "eslint-disable",
    ],
    "components": [
        "lucide", "icon", "pill", "badge", "dashboard", "stat-card", "hero",
    ],
    "duplication": [
        "duplicate", "repeated", "copy-paste", "identical", "same hex",
        "same className",
    ],
    "dead code": [
        "commented-out", "unused import", "unreachable", "empty handler",
        "empty css", "unused state", "deprecated", "console", "dead code",
        "no-op", "todo", "fixme",
    ],
    "accessibility": [
        "accessibility", "a11y", "aria", "alt text", "htmlfor",
        "focus", "contrast ratio", "skip-to-content",
    ],
}


def categorize_issue(text: str) -> str:
    """Infer an issue category from a description string.

    Scores every category by counting keyword hits and returns the
    best match.  This is the **single source of truth** used by scan,
    autofix, plan, status, and any other module that needs to bucket
    issues.
    """
    lowered = text.lower()
    best_cat = "other"
    best_count = 0
    for cat, keywords in ISSUE_CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in lowered)
        if count > best_count:
            best_count = count
            best_cat = cat
    return best_cat


def get_current_scores() -> tuple[dict, dict]:
    """Load state and compute design scores in one step.

    Returns:
        A ``(state, scores)`` tuple where *state* is the full state dict
        and *scores* is the result of :func:`compute_design_score`.

    This eliminates the repeated ``state = load_state(); scores =
    compute_design_score(state)`` two-liner used across 8+ call sites.
    """
    # Deferred import to avoid circular dependency (state → utils → state).
    from uidetox.state import load_state  # noqa: E402

    state = load_state()
    scores = compute_design_score(state)
    return state, scores
