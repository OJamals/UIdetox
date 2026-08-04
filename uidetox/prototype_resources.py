"""Bound untrusted redesign evidence rendered into prototype briefs."""

from __future__ import annotations

import json
from heapq import nsmallest

MAX_BRIEF_BYTES = 65_536
MAX_DIRECTION_SCALAR_BYTES = 2_048
MAX_DIRECTION_LIST_BYTES = 4_096
MAX_BASELINE_BYTES = 4_096
MAX_RUNTIME_REMEDIATION_BYTES = 2_048
MAX_EXPERIENCE_SECTION_BYTES = 16_384
MAX_MIGRATION_EVIDENCE_BYTES = 2_048
MAX_CONTRACT_FINDING_BYTES = 8_192
MAX_OBSERVABLE_CHECK_BYTES = 8_192
MAX_SOURCE_TARGET_BYTES = 8_192
MAX_PRESERVED_CONTRACT_BYTES = 16_384
MAX_FRESHNESS_BYTES = 32_768
MAX_BLOCKER_BYTES = 16_384
MAX_UNKNOWN_BYTES = 8_192
MAX_CONTRACT_COUNT_BYTES = 4_096
MAX_EVIDENCE_LINE_BYTES = 4_096
MAX_RUNTIME_MODULES = 1
MAX_RUNTIME_ANCHORS = 1
MAX_SECTION_ROWS = 10_000


def evidence_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def required_json(value: object, *, max_bytes: int, section: str) -> str:
    """Serialize canonical JSON while stopping at the section byte ceiling."""

    _require_json_scalar_budget(value, max_bytes=max_bytes, section=section)
    chunks: list[str] = []
    size = 0
    encoder = json.JSONEncoder(
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    for chunk in encoder.iterencode(value):
        size += len(chunk.encode("utf-8"))
        if size > max_bytes:
            raise ValueError(
                f"Prototype brief cannot retain required {section} "
                "within resource budget."
            )
        chunks.append(chunk)
    return "".join(chunks)


def _require_json_scalar_budget(
    value: object,
    *,
    max_bytes: int,
    section: str,
) -> None:
    pending = [value]
    seen_containers: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if len(item) > max_bytes:
                raise ValueError(
                    f"Prototype brief cannot retain required {section} "
                    "within resource budget."
                )
            continue
        if not isinstance(item, (dict, list, tuple)):
            continue
        identity = id(item)
        if identity in seen_containers:
            continue
        seen_containers.add(identity)
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
        else:
            pending.extend(item)


def evidence_text(value: object) -> str:
    """Render one untrusted scalar without permitting line-boundary injection."""

    encoded = json.dumps(str(value), ensure_ascii=True)
    return encoded[1:-1]


def clip_evidence_text(value: object, *, max_bytes: int) -> str:
    prefix_truncated = isinstance(value, str) and len(value) > max_bytes
    rendered = evidence_text(value[:max_bytes] if prefix_truncated else value)
    if not prefix_truncated and len(rendered.encode("utf-8")) <= max_bytes:
        return rendered
    suffix = "... [value omitted by resource budget]"
    return rendered[: max(0, max_bytes - len(suffix))] + suffix


def bounded_json_value(
    value: object,
    *,
    depth: int = 0,
) -> object:
    if depth >= 4:
        return "[nested value omitted by resource budget]"
    if isinstance(value, str):
        return value[:96] + (
            "... [value omitted by resource budget]" if len(value) > 96 else ""
        )
    if isinstance(value, dict):
        items = nsmallest(8, value.items(), key=lambda item: str(item[0]))
        bounded = {
            str(key)[:96]: bounded_json_value(item, depth=depth + 1)
            for key, item in items
        }
        if len(value) > 8:
            bounded["uidetox_omitted_key_count"] = len(value) - 8
        return bounded
    if isinstance(value, (list, tuple)):
        bounded = [bounded_json_value(item, depth=depth + 1) for item in value[:8]]
        if len(value) > 8:
            bounded.append({"uidetox_omitted_item_count": len(value) - 8})
        return bounded
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return clip_evidence_text(value, max_bytes=96)


def required_lines(
    lines: list[str],
    *,
    max_bytes: int,
    section: str,
) -> list[str]:
    if _lines_size(lines) > max_bytes:
        raise ValueError(
            f"Prototype brief cannot retain required {section} within resource budget."
        )
    return lines


def required_bullets(
    items: tuple[str, ...],
    *,
    max_bytes: int,
    section: str,
) -> list[str]:
    """Render required bullets without materializing evidence beyond the ceiling."""

    if not items:
        return ["- None recorded."]
    lines: list[str] = []
    size = 0
    for item in items:
        separator_bytes = 1 if lines else 0
        remaining = max_bytes - size - separator_bytes
        if isinstance(item, str) and len(item) + 2 > remaining:
            raise ValueError(
                f"Prototype brief cannot retain required {section} "
                "within resource budget."
            )
        line = f"- {evidence_text(item)}"
        size += len(line.encode("utf-8")) + separator_bytes
        if size > max_bytes:
            raise ValueError(
                f"Prototype brief cannot retain required {section} "
                "within resource budget."
            )
        lines.append(line)
    return lines


def require_row_budget(count: int, *, section: str) -> None:
    if count > MAX_SECTION_ROWS:
        raise ValueError(
            f"Prototype brief cannot inspect {section} beyond "
            f"{MAX_SECTION_ROWS}-row resource budget."
        )


def require_collection_row_budget(value: object, *, section: str) -> None:
    if isinstance(value, (list, tuple)):
        require_row_budget(len(value), section=section)


def bounded_lines(
    entries: list[tuple[str, str]],
    *,
    max_bytes: int,
    overflow_label: str,
    sort_entries: bool = True,
) -> list[str]:
    if not entries:
        return []
    require_row_budget(len(entries), section=overflow_label)
    normalized = [
        (
            clip_evidence_text(category, max_bytes=256),
            _clip_rendered_line(line, max_bytes=MAX_EVIDENCE_LINE_BYTES),
        )
        for category, line in entries
    ]
    ordered = (
        sorted(enumerate(normalized), key=lambda item: (item[1][0], item[1][1]))
        if sort_entries
        else list(enumerate(normalized))
    )
    representative_indexes: list[int] = []
    seen_categories: set[str] = set()
    for index, (category, _line) in ordered:
        if category not in seen_categories:
            seen_categories.add(category)
            representative_indexes.append(index)
    minimum_representative_bytes = 128
    summary_reserve = 128
    if (
        len(representative_indexes) * minimum_representative_bytes + summary_reserve
        > max_bytes
    ):
        raise ValueError(
            "Prototype brief cannot retain representative "
            f"{overflow_label} within resource budget."
        )
    representative_budget = max(
        minimum_representative_bytes,
        (max_bytes - summary_reserve - max(0, len(representative_indexes) - 1))
        // len(representative_indexes),
    )
    representative_lines = {
        index: _clip_rendered_line(
            normalized[index][1],
            max_bytes=representative_budget,
        )
        for index in representative_indexes
    }
    selection_order = representative_indexes + [
        index for index, _entry in ordered if index not in representative_indexes
    ]
    selected: list[tuple[int, str]] = []
    selected_bytes = 0
    for index in selection_order:
        candidate = representative_lines.get(index, normalized[index][1])
        candidate_bytes = len(candidate.encode("utf-8")) + (1 if selected else 0)
        if selected_bytes + candidate_bytes > max_bytes:
            continue
        selected.append((index, candidate))
        selected_bytes += candidate_bytes
    omitted = len(entries) - len(selected)
    if omitted:
        summary = (
            f"- {omitted} additional {overflow_label} remain in the redesign artifact."
        )
        summary_bytes = len(summary.encode("utf-8")) + (1 if selected else 0)
        while selected and selected_bytes + summary_bytes > max_bytes:
            _index, removed = selected.pop()
            selected_bytes -= len(removed.encode("utf-8")) + (1 if selected else 0)
            omitted += 1
            summary = f"- {omitted} additional {overflow_label} remain in the redesign artifact."
            summary_bytes = len(summary.encode("utf-8")) + (1 if selected else 0)
        if selected_bytes + summary_bytes <= max_bytes:
            selected.append((-1, summary))
    return [line for _index, line in selected]


def bounded_bullets(
    items: tuple[str, ...],
    *,
    max_bytes: int,
    overflow_label: str,
) -> list[str]:
    if not items:
        return ["- None recorded."]
    return bounded_lines(
        [("items", _bounded_evidence_line("- ", item)) for item in items],
        max_bytes=max_bytes,
        overflow_label=overflow_label,
        sort_entries=False,
    )


def bounded_numbered(
    items: tuple[str, ...],
    *,
    max_bytes: int,
    overflow_label: str,
) -> list[str]:
    if not items:
        return ["1. None recorded."]
    return bounded_lines(
        [
            ("items", _bounded_evidence_line(f"{index}. ", item))
            for index, item in enumerate(items, start=1)
        ],
        max_bytes=max_bytes,
        overflow_label=overflow_label,
        sort_entries=False,
    )


def bullets(items: tuple[str, ...]) -> list[str]:
    return [f"- {evidence_text(item)}" for item in items] or ["- None recorded."]


def _lines_size(lines: list[str]) -> int:
    return len("\n".join(lines).encode("utf-8"))


def _bounded_evidence_line(prefix: str, value: object) -> str:
    bounded_value = (
        value[:MAX_EVIDENCE_LINE_BYTES]
        if isinstance(value, str) and len(value) > MAX_EVIDENCE_LINE_BYTES
        else value
    )
    return _clip_rendered_line(
        prefix + evidence_text(bounded_value),
        max_bytes=MAX_EVIDENCE_LINE_BYTES,
    )


def _clip_rendered_line(line: str, *, max_bytes: int) -> str:
    if len(line.encode("utf-8")) <= max_bytes:
        return line
    suffix = "... [line omitted by resource budget]"
    return line[: max(0, max_bytes - len(suffix))] + suffix
