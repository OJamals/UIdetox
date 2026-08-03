"""Canonical UI lifecycle vocabulary shared by mapping and redesign output."""

from __future__ import annotations

import re

EXPERIENCE_STATE_BEHAVIOR = {
    "loading": "preserve the surrounding layout and show progress at the affected region without fake content",
    "empty": "preserve active filters and context, distinguish zero results from first use, and offer one relevant next action",
    "error": "preserve entered values and surrounding context, identify the failed action, and provide a direct recovery",
    "success": "reflect the backend-confirmed outcome near the action and remove duplicate-submit ambiguity",
    "disabled": "preserve the control label and readability while explaining the unmet prerequisite nearby",
    "first-run": "preserve the primary job while teaching the first useful action instead of presenting a generic empty state",
}
EXPERIENCE_STATE_ORDER = tuple(EXPERIENCE_STATE_BEHAVIOR)

_ALIASES = {
    "loading": ("loading", "pending", "submitting", "fetching"),
    "empty": ("empty", "nodata", "noresults"),
    "error": ("error", "failed", "failure"),
    "success": ("success", "saved", "complete", "completed"),
    "disabled": ("disabled", "unavailable"),
    "first-run": ("firstrun", "firstvisit", "onboarding"),
}
_RESTRICTED_ALIAS_PREFIXES = {
    "nodata": {"is", "has", "show"},
    "noresults": {"is", "has", "show"},
    "pending": {"is", "has", "request", "query", "form", "submit", "mutation"},
    "saved": {"is", "has", "form", "save", "submit", "mutation"},
    "complete": {"is", "has", "form", "save", "submit", "request", "mutation"},
    "completed": {"is", "has", "form", "save", "submit", "request", "mutation"},
    "unavailable": {"is", "has", "form", "control", "button", "action"},
    "firstrun": {"is", "has"},
    "firstvisit": {"is", "has"},
    "onboarding": {"is", "has"},
}
_TOKEN_SUFFIX_ALIASES = {
    "loading",
    "empty",
    "submitting",
    "fetching",
    "error",
    "failed",
    "failure",
    "success",
    "disabled",
}
_NEGATING_TOKENS = {"no", "non", "not", "off", "un", "without"}
_READ_STATES = ("loading", "empty", "error", "success", "first-run")
_MUTATION_STATES = ("loading", "error", "success", "disabled")


def normalize_experience_state(value: object) -> str | None:
    """Return a canonical state for a state-like identifier, without infix guesses."""

    if not isinstance(value, str):
        return None
    tokenized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", value)
    tokenized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tokenized)
    tokens = tuple(re.findall(r"[a-z0-9]+", tokenized.lower()))
    normalized = "".join(tokens)
    if not normalized:
        return None
    for state in EXPERIENCE_STATE_ORDER:
        for alias in _ALIASES[state]:
            if normalized == alias:
                return state
            allowed_prefixes = _RESTRICTED_ALIAS_PREFIXES.get(alias)
            if allowed_prefixes is not None and normalized.endswith(alias):
                if normalized[: -len(alias)] in allowed_prefixes:
                    return state
                continue
            if (
                alias in _TOKEN_SUFFIX_ALIASES
                and tokens[-1] == alias
                and (len(tokens) == 1 or tokens[-2] not in _NEGATING_TOKENS)
            ):
                return state
    return None


def normalize_experience_states(value: object) -> tuple[str, ...] | None:
    """Validate and normalize a serialized state collection."""

    if not isinstance(value, (list, tuple)):
        return None
    normalized = [normalize_experience_state(item) for item in value]
    if any(state is None for state in normalized):
        return None
    found = set(normalized)
    return tuple(state for state in EXPERIENCE_STATE_ORDER if state in found)


def required_experience_states(*, mutation: bool) -> tuple[str, ...]:
    """Return UX states required for one read or mutation owner."""

    return _MUTATION_STATES if mutation else _READ_STATES
