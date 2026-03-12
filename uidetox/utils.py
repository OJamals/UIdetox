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


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse an ISO timestamp safely, returning ``None`` on failure."""
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _latest_issue_activity(state: dict) -> datetime | None:
    """Return the most recent queue mutation timestamp.

    Pending issues contribute ``created_at`` timestamps; resolved issues
    contribute ``resolved_at`` timestamps.
    """
    latest: datetime | None = None
    for issue in state.get("issues", []):
        created_at = _parse_iso(issue.get("created_at"))
        if created_at is not None and (latest is None or created_at > latest):
            latest = created_at
    for issue in state.get("resolved", []):
        resolved_at = _parse_iso(issue.get("resolved_at"))
        if resolved_at is not None and (latest is None or resolved_at > latest):
            latest = resolved_at
    return latest


def get_score_freshness(state: dict) -> dict:
    """Return whether score data is fresh enough to permit finishing.

    High blended scores are not sufficient on their own: the loop should
    only finish after a fresh objective analysis AND a fresh subjective
    review that both post-date the latest queue mutations.
    """
    last_scan_at = _parse_iso(state.get("last_scan"))
    latest_issue_activity = _latest_issue_activity(state)

    subjective = state.get("subjective", {})
    review_history = subjective.get("history", [])
    latest_review_at: datetime | None = None
    for entry in review_history:
        reviewed_at = _parse_iso(entry.get("timestamp"))
        if reviewed_at is not None and (latest_review_at is None or reviewed_at > latest_review_at):
            latest_review_at = reviewed_at

    objective_fresh = bool(
        last_scan_at is not None
        and (latest_issue_activity is None or last_scan_at >= latest_issue_activity)
    )
    subjective_fresh = bool(
        latest_review_at is not None
        and last_scan_at is not None
        and latest_review_at >= last_scan_at
        and (latest_issue_activity is None or latest_review_at >= latest_issue_activity)
    )

    reasons: list[str] = []
    if last_scan_at is None:
        reasons.append("no objective scan recorded")
    elif latest_issue_activity is not None and last_scan_at < latest_issue_activity:
        reasons.append("objective analysis predates the latest fixes or queue changes")

    if latest_review_at is None:
        reasons.append("no timestamped subjective review recorded")
    elif last_scan_at is not None and latest_review_at < last_scan_at:
        reasons.append("subjective review predates the latest scan")
    elif latest_issue_activity is not None and latest_review_at < latest_issue_activity:
        reasons.append("subjective review predates the latest fixes or queue changes")

    return {
        "objective_fresh": objective_fresh,
        "subjective_fresh": subjective_fresh,
        "target_ready": objective_fresh and subjective_fresh,
        "last_scan": state.get("last_scan"),
        "latest_review": latest_review_at.isoformat() if latest_review_at else None,
        "latest_issue_activity": latest_issue_activity.isoformat() if latest_issue_activity else None,
        "reasons": reasons,
    }


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


def _apply_subjective_curve(raw_score: int, pending_issues: list[dict]) -> int:
    """Apply diminishing-returns curve and objective-anchored penalties.

    Makes 95-100 achievable only when the codebase is genuinely perfect:

    1. **Exponential compression above 70** — raw 95 → effective ~92.
       Only a raw 100 maps to an effective 100.
    2. **Auto-deductions for pending issues** — each unresolved issue
       mechanically lowers the effective subjective score so the agent
       cannot self-assess perfection while known issues remain.
    3. **Hard ceiling when issues remain** — effective subjective is
       capped at 85 as long as the queue is non-empty.
    4. **Objective cross-gate** — if the objective score is below 90
       the effective subjective is capped at 80, preventing a high
       self-score from masking real problems.

    The curve is: ``effective = 60 + 40 × ((raw − 60) / 40)^2.2``
    for raw > 60.  Below 60 the mapping is linear (1:1).
    """
    if raw_score <= 0:
        return 0

    # ── Step 1: Exponential compression above 60 ──
    CURVE_THRESHOLD = 60
    CURVE_EXPONENT = 2.2
    CURVE_RANGE = 100 - CURVE_THRESHOLD  # 40

    if raw_score <= CURVE_THRESHOLD:
        effective = float(raw_score)
    else:
        overshoot = min((raw_score - CURVE_THRESHOLD) / CURVE_RANGE, 1.0)
        effective = CURVE_THRESHOLD + CURVE_RANGE * (overshoot ** CURVE_EXPONENT)

    # ── Step 2: Auto-deductions for pending issues ──
    PENALTY_WEIGHTS = {"T1": 5.0, "T2": 3.0, "T3": 1.5, "T4": 0.75}
    MAX_PENALTY = 30.0

    penalty = 0.0
    for issue in pending_issues:
        tier = issue.get("tier", "T4")
        penalty += PENALTY_WEIGHTS.get(tier, 0.75)
    penalty = min(penalty, MAX_PENALTY)
    effective -= penalty

    # ── Step 3: Hard ceiling when issues are pending ──
    if pending_issues:
        effective = min(effective, 80.0)

    return max(0, min(100, int(effective)))


def compute_design_score(state: dict) -> dict:
    """Compute the blended design score from state.

    Returns a dict with:
      - objective_score: int (0-100) from static analysis slop ratio
      - subjective_score: int | None — raw LLM self-assessment
      - effective_subjective: int | None — after curve + penalties
      - blended_score: int (0-100) final blended score
      - current_slop: weighted slop points remaining
      - resolved_slop: weighted slop points resolved
      - total_slop: total weighted slop points

    The blended score uses the *effective* subjective (post-curve),
    not the raw self-assessment, so 95-100 is only reachable when
    the codebase is genuinely clean.
    """
    issues = state.get("issues", [])
    resolved = state.get("resolved", [])
    stats = state.get("stats", {})
    scans_run = stats.get("scans_run", 0)

    # Higher tiers = more critical → heavier penalty on the score
    tier_weights = {"T1": 15, "T2": 8, "T3": 4, "T4": 2}

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

    # Apply the diminishing-returns curve + objective-anchored penalties
    effective_subjective: int | None = None
    if subjective_score is not None:
        effective_subjective = _apply_subjective_curve(subjective_score, issues)
        # Cross-gate: if objective < 95, cap effective subjective at 75
        if objective_score is not None and objective_score < 95:
            effective_subjective = min(effective_subjective, 75)

    if objective_score is None:
        blended = effective_subjective if effective_subjective is not None else 0
    elif effective_subjective is not None:
        blended = int(objective_score * 0.3 + effective_subjective * 0.7)
    else:
        blended = objective_score

    return {
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "effective_subjective": effective_subjective,
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
