"""Shared utilities for UIdetox."""

import shlex
import subprocess
from datetime import datetime, timezone

SUBJECTIVE_RULES = {
    "curve_threshold": 60,
    "curve_exponent": 2.2,
    "tier_penalty_weights": {"T1": 5.0, "T2": 3.0, "T3": 1.5, "T4": 0.75},
    "max_pending_penalty": 30.0,
    "pending_issue_cap": 80,
    "critical_issue_cap": 70,
    "objective_cap_threshold": 95,
    "objective_cap": 75,
}


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


def _latest_subjective_review_at(state: dict) -> datetime | None:
    """Return the most recent subjective-review timestamp available."""
    subjective = state.get("subjective", {})
    latest_review_at: datetime | None = _parse_iso(subjective.get("reviewed_at"))
    review_history = subjective.get("history", [])
    for entry in review_history:
        reviewed_at = _parse_iso(entry.get("timestamp"))
        if reviewed_at is not None and (latest_review_at is None or reviewed_at > latest_review_at):
            latest_review_at = reviewed_at
    return latest_review_at


def get_score_freshness(state: dict) -> dict:
    """Return whether score data is fresh enough to permit finishing.

    High blended scores are not sufficient on their own: the loop should
    only finish after a fresh objective analysis AND a fresh subjective
    review that both post-date the latest queue mutations.
    """
    last_scan_at = _parse_iso(state.get("last_scan"))
    latest_issue_activity = _latest_issue_activity(state)

    latest_review_at = _latest_subjective_review_at(state)

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


def _coerce_score(value: object) -> int | None:
    """Normalize unknown score inputs into an int score in [0, 100]."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, min(100, int(round(value))))
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return max(0, min(100, int(round(float(raw)))))
        except ValueError:
            return None
    return None


def compute_effective_subjective(
    raw_score: int,
    pending_issues: list[dict],
    *,
    objective_score: int | None = None,
) -> dict[str, object]:
    """Compute effective subjective score with deterministic penalties/caps."""
    rules = SUBJECTIVE_RULES
    normalized_raw = max(0, min(100, int(raw_score)))
    threshold = int(rules["curve_threshold"])
    exponent = float(rules["curve_exponent"])
    curve_range = 100 - threshold

    if normalized_raw <= threshold:
        curve_score = float(normalized_raw)
    else:
        overshoot = min((normalized_raw - threshold) / curve_range, 1.0)
        curve_score = threshold + curve_range * (overshoot ** exponent)

    penalty_weights = rules["tier_penalty_weights"]  # type: ignore[assignment]
    max_penalty = float(rules["max_pending_penalty"])
    pending_penalty = 0.0
    t1_pending = 0
    for issue in pending_issues:
        tier = issue.get("tier", "T4")
        if tier == "T1":
            t1_pending += 1
        pending_penalty += penalty_weights.get(tier, penalty_weights["T4"])  # type: ignore[index]
    pending_penalty = min(pending_penalty, max_penalty)

    effective = curve_score - pending_penalty
    caps_applied: list[str] = []

    if pending_issues:
        pending_cap = int(rules["pending_issue_cap"])
        if effective > pending_cap:
            caps_applied.append("pending_issue_cap")
        effective = min(effective, pending_cap)

    if t1_pending > 0:
        critical_cap = int(rules["critical_issue_cap"])
        if effective > critical_cap:
            caps_applied.append("critical_issue_cap")
        effective = min(effective, critical_cap)

    if objective_score is not None and objective_score < int(rules["objective_cap_threshold"]):
        objective_cap = int(rules["objective_cap"])
        if effective > objective_cap:
            caps_applied.append("objective_cross_gate")
        effective = min(effective, objective_cap)

    effective_score = max(0, min(100, int(round(effective))))

    return {
        "raw_score": normalized_raw,
        "curve_score": int(round(curve_score)),
        "pending_penalty": round(pending_penalty, 2),
        "pending_issue_count": len(pending_issues),
        "critical_issue_count": t1_pending,
        "objective_score": objective_score,
        "caps_applied": caps_applied,
        "effective_score": effective_score,
    }


def _apply_subjective_curve(raw_score: int, pending_issues: list[dict]) -> int:
    """Backward-compatible wrapper around ``compute_effective_subjective``.

    Keeps legacy call sites/tests working while centralizing scoring logic
    in one function that also powers ``compute_design_score``.
    """
    details = compute_effective_subjective(raw_score, pending_issues)
    return int(details["effective_score"])


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

    subjective_score = _coerce_score(state.get("subjective", {}).get("score"))

    # Apply the diminishing-returns curve + objective-anchored penalties
    effective_subjective: int | None = None
    effective_subjective_details: dict[str, object] | None = None
    if subjective_score is not None:
        effective_subjective_details = compute_effective_subjective(
            subjective_score,
            issues,
            objective_score=objective_score,
        )
        effective_subjective = int(effective_subjective_details["effective_score"])

    if objective_score is None:
        blended = effective_subjective if effective_subjective is not None else 0
    elif effective_subjective is not None:
        blended = int(round(objective_score * 0.3 + effective_subjective * 0.7))
    else:
        blended = objective_score

    return {
        "objective_score": objective_score,
        "subjective_score": subjective_score,
        "effective_subjective": effective_subjective,
        "effective_subjective_details": effective_subjective_details,
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
