"""Skill recommendation engine: maps issue patterns and codebase signals to relevant skills.

This module dynamically reads skill command markdown files, extracts metadata,
and recommends skills based on current issue queue contents, design dial values,
and codebase characteristics.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Skill taxonomy — keyword → skill mappings for auto-invocation
# Organised by category so the loop can reason about *what phase* a skill
# belongs to (diagnose / fix / style-tune / content).
# ---------------------------------------------------------------------------

SKILL_TAXONOMY: dict[str, dict[str, Any]] = {
    # ── Diagnose ──────────────────────────────────────────────────────────
    "scan": {
        "description": "Full diagnostic audit of frontend interface quality.",
        "category": "diagnose",
        "phase": "scan",
        "keywords": [
            "scan", "diagnostic", "issue list", "priority", "severity",
            "tier", "score", "analysis", "anti-pattern",
        ],
        "trigger_when": "always_first",
    },
    "audit": {
        "description": "Comprehensive audit: accessibility, performance, theming, responsive.",
        "category": "diagnose",
        "phase": "scan",
        "keywords": [
            "audit", "accessibility", "a11y", "performance", "theming",
            "responsive", "WCAG", "contrast", "compliance",
        ],
        "trigger_when": "post_scan",
    },
    "critique": {
        "description": "Evaluate design effectiveness: hierarchy, IA, emotional resonance.",
        "category": "diagnose",
        "phase": "review",
        "keywords": [
            "critique", "review", "hierarchy", "information architecture",
            "emotional", "design quality", "UX evaluation",
        ],
        "trigger_when": "post_fix",
    },
    "setup": {
        "description": "Gather project design context and configure dials.",
        "category": "diagnose",
        "phase": "setup",
        "keywords": [
            "setup", "configuration", "design system", "dials",
            "DESIGN_VARIANCE", "MOTION_INTENSITY", "VISUAL_DENSITY",
            "framework", "initialize",
        ],
        "trigger_when": "always_first",
    },

    # ── Fix / Iterate ─────────────────────────────────────────────────────
    "fix": {
        "description": "Interactive fix loop — pick, apply, verify, repeat.",
        "category": "fix",
        "phase": "fix",
        "keywords": [
            "fix", "issue", "resolve", "scan results", "priority",
            "queue", "loop", "anti-pattern", "tier",
        ],
        "trigger_when": "queue_non_empty",
    },
    "normalize": {
        "description": "Normalise design to match design system, ensure consistency.",
        "category": "fix",
        "phase": "fix",
        "keywords": [
            "design system", "consistency", "normalize", "standardize",
            "token alignment", "spacing system", "typography scale",
            "component alignment", "brand compliance",
        ],
        "trigger_when": "issue_match",
    },
    "harden": {
        "description": "Improve resilience: error handling, i18n, overflow, edge cases.",
        "category": "fix",
        "phase": "fix",
        "keywords": [
            "error handling", "edge case", "i18n", "internationalization",
            "overflow", "truncation", "resilience", "robustness",
            "production", "fallback", "loading state", "empty state",
            "error boundary", "RTL", "graceful degradation",
        ],
        "trigger_when": "issue_match",
    },
    "optimize": {
        "description": "Improve performance: loading, rendering, images, bundle size.",
        "category": "fix",
        "phase": "fix",
        "keywords": [
            "performance", "loading speed", "rendering", "bundle size",
            "lazy loading", "image optimization", "code splitting",
            "Core Web Vitals", "LCP", "CLS", "memoization",
        ],
        "trigger_when": "issue_match",
    },
    "extract": {
        "description": "Extract reusable components, tokens, patterns for design system.",
        "category": "fix",
        "phase": "fix",
        "keywords": [
            "design system", "component library", "design tokens",
            "reusable", "pattern", "shared component", "extract",
            "consolidate", "variant", "DRY", "refactor",
        ],
        "trigger_when": "issue_match",
    },

    # ── Style Tuning ──────────────────────────────────────────────────────
    "bolder": {
        "description": "Amplify safe/boring designs — increase visual impact.",
        "category": "style",
        "phase": "fix",
        "keywords": [
            "bold", "impact", "visual interest", "typography scale",
            "saturation", "contrast", "hero", "dramatic", "personality",
            "memorable", "amplify", "vibrant",
        ],
        "trigger_when": "dial_low_variance",
        "dial_condition": {"DESIGN_VARIANCE": (">=", 7)},
    },
    "quieter": {
        "description": "Tone down overly bold or aggressive designs.",
        "category": "style",
        "phase": "fix",
        "keywords": [
            "quiet", "subtle", "refined", "desaturate", "soften",
            "muted", "sophisticated", "restrained", "elegant", "calm",
            "gentle", "minimalist",
        ],
        "trigger_when": "dial_high_variance",
        "dial_condition": {"DESIGN_VARIANCE": ("<=", 3)},
    },
    "colorize": {
        "description": "Add strategic colour to monochromatic features.",
        "category": "style",
        "phase": "fix",
        "keywords": [
            "color", "palette", "monochromatic", "hue", "saturation",
            "accent color", "tinted gray", "brand color", "color system",
            "semantic color", "expressive",
        ],
        "trigger_when": "issue_match",
    },
    "animate": {
        "description": "Add purposeful animations and micro-interactions.",
        "category": "style",
        "phase": "fix",
        "keywords": [
            "animation", "motion", "transition", "micro-interaction",
            "keyframe", "easing", "hover", "entrance", "exit",
            "loading animation", "framer motion", "scroll animation",
        ],
        "trigger_when": "dial_motion",
        "dial_condition": {"MOTION_INTENSITY": (">=", 5)},
    },
    "distill": {
        "description": "Strip to essence — remove unnecessary complexity.",
        "category": "style",
        "phase": "fix",
        "keywords": [
            "simplify", "reduce", "minimal", "clean", "clutter",
            "complexity", "essential", "streamline", "whitespace",
            "cognitive load", "declutter",
        ],
        "trigger_when": "issue_match",
    },
    "polish": {
        "description": "Final quality pass — alignment, spacing, consistency details.",
        "category": "style",
        "phase": "review",
        "keywords": [
            "polish", "alignment", "spacing", "pixel-perfect",
            "consistency", "detail", "ship-ready", "final pass",
            "quality", "refinement", "visual rhythm",
        ],
        "trigger_when": "post_fix",
    },
    "delight": {
        "description": "Add moments of joy, personality, unexpected touches.",
        "category": "style",
        "phase": "review",
        "keywords": [
            "delight", "joy", "personality", "micro-interaction",
            "empty state", "success state", "easter egg", "celebration",
            "whimsy", "surprise", "emotional design", "playful",
        ],
        "trigger_when": "post_fix",
    },

    # ── Content & UX ──────────────────────────────────────────────────────
    "clarify": {
        "description": "Improve unclear UX copy, error messages, microcopy, labels.",
        "category": "content",
        "phase": "fix",
        "keywords": [
            "copy", "UX writing", "microcopy", "error message", "label",
            "placeholder", "CTA", "button text", "instructions",
            "jargon", "ambiguity", "tone", "help text", "tooltip",
            "clarity", "wording",
        ],
        "trigger_when": "issue_match",
    },
    "onboard": {
        "description": "Design/improve onboarding, empty states, first-time experiences.",
        "category": "content",
        "phase": "fix",
        "keywords": [
            "onboarding", "first-time", "welcome", "tutorial",
            "walkthrough", "empty state", "getting started",
            "time to value", "progressive disclosure", "setup wizard",
            "new user",
        ],
        "trigger_when": "issue_match",
    },
    "adapt": {
        "description": "Adapt designs across screen sizes, devices, platforms.",
        "category": "content",
        "phase": "fix",
        "keywords": [
            "responsive", "mobile", "tablet", "desktop", "screen size",
            "breakpoints", "touch", "device", "platform", "media query",
            "viewport", "adaptive layout", "progressive enhancement",
        ],
        "trigger_when": "issue_match",
    },
}


def _get_skill_data_dir() -> Path | None:
    """Locate the skills data directory.

    Checks bundled package data first, then falls back to the project
    root commands/ directory for editable installs / development.
    """
    pkg_data = Path(__file__).resolve().parent / "data" / "commands"
    if pkg_data.is_dir():
        return pkg_data
    # Fallback: project root commands/ (editable install)
    project_root = Path(__file__).resolve().parent.parent / "commands"
    if project_root.is_dir():
        return project_root
    return None


def list_all_skills() -> list[str]:
    """Return sorted list of all available skill names."""
    return sorted(SKILL_TAXONOMY.keys())


def get_skill_info(skill_name: str) -> dict[str, Any] | None:
    """Return taxonomy info for a given skill, or None."""
    return SKILL_TAXONOMY.get(skill_name)


def get_skill_content(skill_name: str) -> str | None:
    """Read and return the full markdown content for a skill."""
    data_dir = _get_skill_data_dir()
    if not data_dir:
        return None
    md_path = data_dir / f"{skill_name}.md"
    if md_path.exists():
        try:
            return md_path.read_text(encoding="utf-8")
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Recommendation engine
# ---------------------------------------------------------------------------

def recommend_skills_for_issues(
    issues: list[dict[str, Any]],
    *,
    config: dict[str, Any] | None = None,
    phase: str = "fix",
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Recommend skills based on the current issue queue and design dials.

    Returns a list of dicts: [{"skill": name, "reason": str, "priority": int, "category": str}]
    Sorted by priority (lower = higher priority).
    """
    if config is None:
        config = {}

    # Build a combined text blob from all issues for keyword matching
    combined_text = " ".join(
        (i.get("issue", "") + " " + i.get("command", "") + " " + i.get("file", ""))
        for i in issues
    ).lower()

    recommendations: list[dict[str, Any]] = []
    seen_skills: set[str] = set()

    for skill_name, info in SKILL_TAXONOMY.items():
        if skill_name in seen_skills:
            continue

        score = 0
        reasons: list[str] = []
        category = info.get("category", "unknown")
        skill_phase = info.get("phase", "fix")

        # Skip setup/scan skills during fix phase (they're invoked separately)
        if phase == "fix" and skill_phase == "setup":
            continue

        # 1. Keyword matching against issue queue
        keyword_hits = 0
        for kw in info.get("keywords", []):
            if kw.lower() in combined_text:
                keyword_hits += 1

        if keyword_hits > 0:
            score += keyword_hits * 10
            reasons.append(f"{keyword_hits} issue keyword match(es)")

        # 2. Design dial conditions
        dial_cond = info.get("dial_condition", {})
        for dial_name, (op, threshold) in dial_cond.items():
            dial_val = config.get(dial_name, 5)
            if op == ">=" and dial_val >= threshold:
                score += 20
                reasons.append(f"{dial_name}={dial_val} (>={threshold})")
            elif op == "<=" and dial_val <= threshold:
                score += 20
                reasons.append(f"{dial_name}={dial_val} (<={threshold})")

        # 3. Phase alignment bonus
        if skill_phase == phase:
            score += 5

        # 4. Trigger-based scoring
        trigger = info.get("trigger_when", "issue_match")
        if trigger == "queue_non_empty" and len(issues) > 0 and phase == "fix":
            score += 15
            reasons.append("queue has issues")
        elif trigger == "post_fix" and phase == "review":
            score += 25
            reasons.append(f"post-fix {phase} phase")
        elif trigger == "post_scan" and phase == "scan":
            score += 15
            reasons.append("post-scan analysis")

        # 5. Issue tier weighting — T1/T2 issues in matching categories boost score
        for issue in issues:
            tier = issue.get("tier", "T4")
            desc = (issue.get("issue", "") + " " + issue.get("command", "")).lower()
            if tier in ("T1", "T2"):
                for kw in info.get("keywords", [])[:5]:  # top keywords only
                    if kw.lower() in desc:
                        score += 5
                        break

        if score > 0:
            recommendations.append({
                "skill": skill_name,
                "description": info["description"],
                "reason": "; ".join(reasons),
                "priority": 1000 - score,  # lower = better
                "category": category,
                "score": score,
            })
            seen_skills.add(skill_name)

    # Sort by priority (ascending = best first)
    recommendations.sort(key=lambda r: r["priority"])
    return recommendations[:limit]


def recommend_review_skills(
    *,
    config: dict[str, Any] | None = None,
    issues_remaining: int = 0,
    blended_score: float | None = None,
) -> list[dict[str, Any]]:
    """Recommend skills for the review/re-scan phase (Stage 3 of the loop).

    These are skills that should be invoked after fixes are complete
    to evaluate and enhance the overall quality.
    """
    if config is None:
        config = {}

    recommendations: list[dict[str, Any]] = []

    # Always recommend critique + polish in review phase
    for skill_name in ("critique", "polish", "delight"):
        info = SKILL_TAXONOMY.get(skill_name)
        if info:
            recommendations.append({
                "skill": skill_name,
                "description": info["description"],
                "reason": "standard review-phase skill",
                "category": info.get("category", "style"),
            })

    # If score is low, recommend audit for comprehensive re-assessment
    if blended_score is not None and blended_score < 70:
        info = SKILL_TAXONOMY.get("audit")
        if info:
            recommendations.append({
                "skill": "audit",
                "description": info["description"],
                "reason": f"score {blended_score} < 70 — comprehensive audit recommended",
                "category": "diagnose",
            })

    # Dial-driven review skills
    variance = config.get("DESIGN_VARIANCE", 5)
    motion = config.get("MOTION_INTENSITY", 5)

    if variance >= 7:
        info = SKILL_TAXONOMY.get("bolder")
        if info:
            recommendations.append({
                "skill": "bolder",
                "description": info["description"],
                "reason": f"DESIGN_VARIANCE={variance} — amplify visual impact",
                "category": "style",
            })
    elif variance <= 3:
        info = SKILL_TAXONOMY.get("quieter")
        if info:
            recommendations.append({
                "skill": "quieter",
                "description": info["description"],
                "reason": f"DESIGN_VARIANCE={variance} — refine visual subtlety",
                "category": "style",
            })

    if motion >= 6:
        info = SKILL_TAXONOMY.get("animate")
        if info:
            recommendations.append({
                "skill": "animate",
                "description": info["description"],
                "reason": f"MOTION_INTENSITY={motion} — enhance animations",
                "category": "style",
            })

    return recommendations


def get_skill_cli_command(skill_name: str, target: str = ".") -> str:
    """Return the CLI command string to invoke a skill."""
    return f"uidetox {skill_name} {target}"


def format_skill_recommendations(
    recommendations: list[dict[str, Any]],
    *,
    indent: str = "    ",
    show_commands: bool = True,
    target: str = ".",
) -> str:
    """Format skill recommendations for terminal output."""
    if not recommendations:
        return ""

    lines: list[str] = []

    # Group by category
    categories: dict[str, list[dict[str, Any]]] = {}
    for rec in recommendations:
        cat = rec.get("category", "other")
        categories.setdefault(cat, []).append(rec)

    category_labels = {
        "diagnose": "🔍 Diagnostic",
        "fix": "🔧 Fix & Improve",
        "style": "🎨 Style Tuning",
        "content": "📝 Content & UX",
    }

    for cat, cat_label in category_labels.items():
        recs = categories.get(cat, [])
        if not recs:
            continue
        lines.append(f"{indent}{cat_label}:")
        for rec in recs:
            skill = rec["skill"]
            desc = rec["description"]
            reason = rec.get("reason", "")
            lines.append(f"{indent}  • {skill:12s} — {desc}")
            if reason:
                lines.append(f"{indent}    Reason: {reason}")
            if show_commands:
                lines.append(f"{indent}    Run: uidetox {skill} {target}")
        lines.append("")

    return "\n".join(lines)
