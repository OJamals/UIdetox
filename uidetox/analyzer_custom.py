"""Custom analyzer heuristics and handler registry."""

import re
from pathlib import Path

from uidetox.analyzer_ast import has_ast_for


_REDUCED_MOTION_MEDIA = re.compile(
    r"@media\s*\([^)]*prefers-reduced-motion\s*:\s*reduce[^)]*\)\s*\{",
    re.IGNORECASE,
)
_REDUCED_MOTION_OVERRIDE_PROPERTIES = {
    "animation",
    "animation-delay",
    "animation-duration",
    "animation-iteration-count",
    "scroll-behavior",
    "transition",
    "transition-delay",
    "transition-duration",
}


def _issue_for_match(
    rule: dict,
    filepath: Path,
    content: str,
    match: re.Match[str],
) -> dict:
    line = content.count("\n", 0, match.start()) + 1
    column = match.start() - content.rfind("\n", 0, match.start())
    lines = content.splitlines()
    return {
        "id": rule["id"],
        "file": str(filepath.resolve()),
        "tier": rule["tier"],
        "issue": rule["description"],
        "command": rule["command"],
        "line": line,
        "column": column,
        "snippet": lines[line - 1].strip() if line <= len(lines) else "",
    }


def _reduced_motion_ranges(content: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for media in _REDUCED_MOTION_MEDIA.finditer(content):
        opening = content.find("{", media.start(), media.end())
        if opening < 0:
            continue
        depth = 0
        for index in range(opening, len(content)):
            if content[index] == "{":
                depth += 1
            elif content[index] == "}":
                depth -= 1
                if depth == 0:
                    ranges.append((opening, index))
                    break
    return tuple(ranges)


def _inside_ranges(offset: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= offset <= end for start, end in ranges)


def _important_property(content: str, offset: int) -> str | None:
    declaration_start = max(
        content.rfind(";", 0, offset),
        content.rfind("{", 0, offset),
    )
    declaration = content[declaration_start + 1 : offset]
    match = re.search(r"([-\w]+)\s*:\s*[^;{}]*$", declaration)
    return match.group(1).lower() if match else None


def _is_visible_markup_text(content: str, start: int, end: int) -> bool:
    last_open = content.rfind("<", 0, start)
    last_close = content.rfind(">", 0, start)
    if last_close < 0 or last_open > last_close or content.find("<", end) < 0:
        return False
    prefix = content[:start].lower()
    for tag in ("script", "style"):
        if prefix.rfind(f"<{tag}") > prefix.rfind(f"</{tag}"):
            return False
    return True


def _analyze_component_layout(filepath: Path, content: str, ext: str) -> list[dict]:
    """Component-level heuristic analysis for layout-level slop detection.

    Analyzes entire file structure, not individual patterns, to detect:
    - Generic dashboard layouts (N identical KPI cards + chart)
    - Feature-grid slop (3-column identical items)
    - Pricing table clichés
    - Hero-section-heavy pages
    - Component files with zero interactivity
    """
    issues = []
    fpath = str(filepath.resolve())

    if ext not in {".tsx", ".jsx"}:
        return issues

    lines = content.splitlines()
    file_len = len(lines)

    # ── Heuristic 1: KPI Card Dashboard Pattern ──
    # Look for repeated card-like structures with metrics/numbers
    card_patterns = re.findall(
        r"(?:<(?:\w+Card|\w+Stat|\w+Metric|\w+KPI)\b[^>]*>)", content, re.IGNORECASE
    )
    chart_patterns = re.findall(
        r"(?:<(?:\w*Chart|\w*Graph|LineChart|BarChart|PieChart|AreaChart|ResponsiveContainer)\b)",
        content,
        re.IGNORECASE,
    )
    if len(card_patterns) >= 4 and len(chart_patterns) >= 1:
        issues.append(
            {
                "id": "DASHBOARD_LAYOUT_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Generic dashboard layout: {len(card_patterns)} KPI/stat cards + {len(chart_patterns)} chart(s) — classic AI dashboard slop.",
                "command": "Replace identical card grid with varied sizes (span-2 hero metric, inline sparklines). Weave data into contextual narrative.",
            }
        )

    # ── Heuristic 2: Feature Grid Slop (identical feature items) ──
    # Detect 3+ identical JSX blocks with icon + heading + description pattern
    feature_block = re.findall(
        r"(?:<(?:div|section|article|li)\s[^>]*>[\s\S]{30,300}?"
        r"(?:<\w+Icon|<Icon\b|icon=|<svg\b)[\s\S]{10,200}?"
        r"(?:<h[23456]|<(?:Title|Heading|CardTitle))"
        r"[\s\S]{10,200}?"
        r"(?:<p\b|<(?:Description|Text|CardDescription))"
        r")",
        content,
        re.IGNORECASE,
    )
    if len(feature_block) >= 3:
        issues.append(
            {
                "id": "FEATURE_GRID_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Feature grid slop: {len(feature_block)} identical icon+heading+description blocks — generic SaaS landing pattern.",
                "command": "Vary feature presentations (alternate image/text, use different card sizes, stagger layouts). Break the 3-column monotony.",
            }
        )

    # ── Heuristic 3: Pricing Table Cliché ──
    pricing_signals = len(
        re.findall(
            r"(?:\$\d+|/mo(?:nth)?|/yr|/year|popular|recommended|enterprise|pro|starter|basic|premium)",
            content,
            re.IGNORECASE,
        )
    )
    pricing_cards = len(
        re.findall(
            r"(?:PricingCard|PricingTier|PricingPlan|price-card)",
            content,
            re.IGNORECASE,
        )
    )
    if pricing_signals >= 6 or pricing_cards >= 3:
        issues.append(
            {
                "id": "PRICING_TABLE_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": "Pricing table cliché detected — 3-column pricing grid with 'Popular' badge is the #1 AI SaaS template.",
                "command": "Design pricing as a comparison flow, slider, or interactive calculator. Vary card sizes. Make the recommended plan visually dominant, not just badged.",
            }
        )

    # ── Heuristic 4: Zero Interactivity File ──
    has_interactivity = bool(
        re.search(
            r"(?:onClick|onChange|onSubmit|onPress|onFocus|onBlur|onKeyDown|onMouseEnter|onHover|hover:|focus:|active:|useState|useReducer|motion\.|animate)",
            content,
        )
    )
    jsx_count = len(re.findall(r"<[A-Z]\w+", content))
    if not has_interactivity and jsx_count >= 5 and file_len > 50:
        issues.append(
            {
                "id": "STATIC_COMPONENT_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Static component detected: {jsx_count} JSX elements but zero interactivity (no handlers, no hover/focus, no animation).",
                "command": "Add hover states, transitions, or micro-interactions. Static pages feel dead — every component should respond to user input.",
            }
        )

    # ── Heuristic 5: Hero Section Heavy Page ──
    hero_count = len(re.findall(r"(?:hero|Hero|HERO)", content))
    section_count = len(re.findall(r"<(?:section|Section)\b", content, re.IGNORECASE))
    if hero_count >= 2 and section_count <= 3:
        issues.append(
            {
                "id": "HERO_HEAVY_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": "Hero-section-heavy page — multiple hero blocks without enough content sections.",
                "command": "A page needs one hero at most. Replace additional heroes with content sections, testimonials, or data-driven blocks.",
            }
        )

    # ── Heuristic 6: Testimonial Grid Slop ──
    testimonial_signals = len(
        re.findall(
            r"(?:testimonial|review|quote|avatar.*?(?:name|title)|rating|stars?.*?(?:5|five))",
            content,
            re.IGNORECASE,
        )
    )
    if testimonial_signals >= 6:
        issues.append(
            {
                "id": "TESTIMONIAL_GRID_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": "Generic testimonial grid detected — avatar + quote + name pattern repeated.",
                "command": "Use varied testimonial layouts: full-width quotes, video testimonials, inline social proof, or rotating carousel with real data.",
            }
        )

    return issues


def _analyze_document_structure_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run document-structure heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "div_soup":
        if has_ast_for(ext):
            return issues  # Handled by AST
        div_count = len(re.findall(r"<div[\s>]", content, re.IGNORECASE))
        semantic_count = len(
            re.findall(
                r"<(?:nav|main|article|section|aside|header|footer)[\s>]",
                content,
                re.IGNORECASE,
            )
        )
        if div_count > 20 and semantic_count == 0:
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({div_count} divs, 0 semantic elements)",
                    "command": rule["command"],
                }
            )
        return issues

    # Custom check: missing_hover — buttons with className but no hover: class

    if custom == "nested_ternary":
        if has_ast_for(ext):
            return issues  # Handled by AST
        # Count nested ternaries: lines with ? ... ? ... : pattern
        ternary_nests = len(re.findall(r"\?[^:?\n]{0,80}\?", content))
        if ternary_nests >= 2:
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({ternary_nests} nested ternaries found)",
                    "command": rule["command"],
                }
            )
        return issues

    # Custom check: disabled_cursor — disabled elements missing cursor-not-allowed

    return None


def _analyze_interaction_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run interaction-state heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "missing_hover":
        for m in re.finditer(
            r'<button[^>]*className=["\']([^"\']*)["\']', content, re.IGNORECASE
        ):
            classes = m.group(1)
            if "hover:" not in classes:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break  # Flag once per file
        return issues

    # Custom check: missing_focus — interactive elements without focus: class
    if custom == "missing_focus":
        for m in re.finditer(
            r'<(?:button|a)\s[^>]*className=["\']([^"\']*)["\']', content, re.IGNORECASE
        ):
            classes = m.group(1)
            if "focus:" not in classes:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break  # Flag once per file
        return issues

    # Custom check: missing_transition — hover: classes without transition-
    if custom == "missing_transition":
        for m in re.finditer(
            r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE
        ):
            classes = m.group(1)
            if "hover:" in classes and "transition" not in classes:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break  # Flag once per file
        return issues

    # Custom check: ugly_scrollbar — overflow scroll without scrollbar styling
    if custom == "ugly_scrollbar":
        for m in re.finditer(
            r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE
        ):
            classes = m.group(1)
            if (
                re.search(r"overflow-[xy]-(?:auto|scroll)", classes)
                and "scrollbar" not in classes
            ):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break  # Flag once per file
        return issues

    # Custom check: nested_ternary — only flag in JSX return blocks (rough heuristic)

    if custom == "disabled_cursor":
        # Find elements with disabled prop/attr
        disabled_elements = re.findall(
            r'(?:disabled|isDisabled)[^>]*class(?:Name)?=["\']([^"\']*)["\']',
            content,
            re.IGNORECASE,
        )
        for classes in disabled_elements:
            if "cursor-not-allowed" not in classes and "disabled:" not in classes:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    return None


def _analyze_commented_code_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Detect blocks of commented-out source."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "commented_code":
        lines = content.splitlines()
        commented_code_lines = 0
        for line in lines:
            stripped = line.strip()
            # Match single-line commented code patterns
            if re.match(
                r"^(?://|/\*|\*|{/\*)\s*(?:"
                r"<[A-Z]|"
                r"(?:const|let|var|function|import|export|return|if|for|while)\s|"
                r"(?:className|onClick|onChange|style)=|"
                r"\w+\.\w+\(|"
                r"\}\s*(?:else|catch|finally)|"
                r"(?:await|async)\s"
                r")",
                stripped,
            ):
                commented_code_lines += 1
        if commented_code_lines >= 3:
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({commented_code_lines} lines of commented-out code)",
                    "command": rule["command"],
                }
            )
        return issues

    # Custom check: unused_import — imports whose identifiers appear nowhere else in the file

    return None


_IMPORT_PATTERN = re.compile(
    r"^import\s+"
    r"(?:"
    r"(?:type\s+)?(\w+)(?:\s*,\s*\{([^}]+)\})?"  # default + named
    r"|\{([^}]+)\}"  # named only
    r"|\*\s+as\s+(\w+)"  # namespace
    r")"
    r'\s+from\s+["\'][^"\']+["\'];?\s*$',
    re.MULTILINE,
)


def _extract_import_names(match: re.Match) -> list[str]:
    """Return local identifiers declared by one import statement."""
    names: list[str] = []
    if match.group(1):
        names.append(match.group(1))
    for group in (match.group(2), match.group(3)):
        if not group:
            continue
        for part in group.split(","):
            part = part.strip()
            if " as " in part:
                part = part.split(" as ")[-1].strip()
            if part and part != "type":
                names.append(part)
    if match.group(4):
        names.append(match.group(4))
    return names


def _find_unused_import_names(content: str) -> list[str]:
    """Return imports referenced only by their declaration."""
    unused_names: list[str] = []
    for match in _IMPORT_PATTERN.finditer(content):
        for name in _extract_import_names(match):
            occurrences = len(re.findall(r"\b" + re.escape(name) + r"\b", content))
            if occurrences <= 1:
                unused_names.append(name)
    return unused_names


def _analyze_unused_import_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Detect imported names unused outside import declarations."""
    if rule.get("_custom_check") != "unused_import":
        return None

    issues = []
    unused_names = _find_unused_import_names(content)
    if unused_names:
        sample = ", ".join(unused_names[:5])
        suffix = f" (+{len(unused_names) - 5} more)" if len(unused_names) > 5 else ""
        issues.append(
            {
                "id": rule["id"],
                "file": str(filepath.resolve()),
                "tier": rule["tier"],
                "issue": f"{rule['description']} Likely unused: {sample}{suffix}",
                "command": rule["command"],
            }
        )
    return issues


def _analyze_unused_state_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Detect useState values never read."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "unused_state":
        for m in re.finditer(r"const\s+\[(\w+),\s*set(\w+)\]\s*=\s*useState", content):
            state_var = m.group(1)
            # Check if state var is referenced beyond the declaration
            occurrences = len(re.findall(r"\b" + re.escape(state_var) + r"\b", content))
            if occurrences <= 1:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"{rule['description']} `{state_var}` appears unused.",
                        "command": rule["command"],
                    }
                )
                break  # Flag once per file
        return issues

    return None


def _analyze_contrast_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run configured color-contrast analysis."""
    issues = []
    custom = rule.get("_custom_check")
    # Custom check: contrast_ratio
    if custom == "contrast_ratio" and dynamic_colors:
        for m in re.finditer(
            r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE
        ):
            classes = m.group(1).split()
            bg_color = None
            text_color = None

            for c in classes:
                if c.startswith("bg-"):
                    bg_name = c[3:].split("/")[0]
                    if bg_name in dynamic_colors:
                        bg_color = dynamic_colors[bg_name]
                elif c.startswith("text-"):
                    text_name = c[5:].split("/")[0]
                    if text_name in dynamic_colors:
                        text_color = dynamic_colors[text_name]

            if bg_color and text_color:
                from uidetox.color_utils import contrast_ratio

                ratio = contrast_ratio(text_color, bg_color)
                if ratio < 4.5:
                    issues.append(
                        {
                            "id": rule["id"],
                            "file": str(filepath.resolve()),
                            "tier": rule["tier"],
                            "issue": f"Low contrast detected: {text_color} on {bg_color} (ratio {ratio:.1f}:1).",
                            "command": rule["command"],
                        }
                    )
                    break
        return issues

    return None


def _analyze_accessibility_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run accessibility and document-shell heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "video_no_captions":
        if re.search(r"<video\b", content, re.IGNORECASE) and not re.search(
            r"<track\b", content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "focus_outline_removed":
        # :focus { outline: none } or :focus { outline: 0 }
        if re.search(
            r":focus\s*\{[^}]*outline:\s*(?:none|0)\b", content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "focus_visible_missing":
        if re.search(r":focus\s*\{", content, re.IGNORECASE) and not re.search(
            r":focus-visible\s*\{", content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "no_select_content":
        if re.search(r"\bselect-none\b", content):
            # Flag if used on non-button elements (not inside <button>)
            # Simple heuristic: flag if it appears in className on a non-button
            if re.search(
                r"<(?!button)(?:[a-z][a-z0-9]*)(?:\s[^>]*)?\bclassName=[^>]*select-none",
                content,
                re.IGNORECASE,
            ):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "outline_none":
        for m_cls in re.finditer(
            r'class(?:Name)?=["\']([^"\']*outline-none[^"\']*)["\']',
            content,
            re.IGNORECASE,
        ):
            cls = m_cls.group(1)
            if "focus-visible:" not in cls and "focus:ring" not in cls:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "reduced_motion_missing":
        for m_cls in re.finditer(
            r'class(?:Name)?=["\']([^"\']*animate-[^"\']*)["\']', content, re.IGNORECASE
        ):
            cls = m_cls.group(1)
            if "motion-reduce:" not in cls:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "missing_meta_description":
        if re.search(r"<head\b", content, re.IGNORECASE) and not re.search(
            r'<meta\s[^>]*name=["\']description["\']', content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "skip_to_content_missing":
        if re.search(r"<nav\b", content, re.IGNORECASE) and re.search(
            r"<main\b", content, re.IGNORECASE
        ):
            if not re.search(r'href=["\']#', content, re.IGNORECASE):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "missing_favicon":
        if re.search(r"<head\b", content, re.IGNORECASE) and not re.search(
            r'rel=["\'](?:shortcut icon|icon)["\']', content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    return None


def _analyze_css_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run CSS foundation heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom in {"important_abuse", "important_animation"}:
        pattern = rule.get("pattern")
        if not isinstance(pattern, re.Pattern):
            return issues
        reduced_motion = _reduced_motion_ranges(content)
        for match in pattern.finditer(content):
            if _inside_ranges(match.start(), reduced_motion):
                if custom == "important_animation":
                    continue
                if (
                    _important_property(content, match.start())
                    in _REDUCED_MOTION_OVERRIDE_PROPERTIES
                ):
                    continue
            issues.append(_issue_for_match(rule, filepath, content, match))
            break
        return issues

    if custom == "css_scroll_behavior":
        if re.search(
            r"scroll-behavior:\s*smooth", content, re.IGNORECASE
        ) and not re.search(r"prefers-reduced-motion", content, re.IGNORECASE):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "sticky_without_top":
        for block_m in re.finditer(
            r"position:\s*sticky[^}]*", content, re.IGNORECASE | re.DOTALL
        ):
            block = block_m.group(0)
            if not re.search(r"\btop\s*:", block, re.IGNORECASE):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "scroll_snap_without_behavior":
        if re.search(r"scroll-snap-type:", content, re.IGNORECASE) and not re.search(
            r"scroll-behavior:", content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "generic_font_family":
        AI_FONTS = re.compile(
            r"font-family:\s*(?:'Inter'|Inter|'Roboto'|Roboto|'Open Sans'|Open Sans|'Montserrat'|Montserrat|'Poppins'|Poppins|'Lato'|Lato)",
            re.IGNORECASE,
        )
        if AI_FONTS.search(content) and not re.search(
            r"-apple-system", content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "font_display_missing":
        for ff_m in re.finditer(
            r"@font-face\s*\{([^}]*)\}", content, re.IGNORECASE | re.DOTALL
        ):
            if "font-display" not in ff_m.group(1):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "alpha_color_abuse":
        count = len(re.findall(r"(?:rgba|hsla)\s*\(", content, re.IGNORECASE))
        if count >= 5:
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} ({count} instances found)",
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "grid_auto_fit_missing":
        if re.search(
            r"grid-template-columns:\s*repeat\(\s*(?:[2-9]|\d{2,})\s*,",
            content,
            re.IGNORECASE,
        ):
            if not re.search(r"auto-fit|auto-fill", content, re.IGNORECASE):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "scroll_smooth_no_motion":
        if re.search(r"\bscroll-smooth\b", content) and not re.search(
            r"motion-reduce:scroll-auto", content
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    return None


def _analyze_tailwind_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run conflicting Tailwind utility heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "tailwind_font_conflict":
        SIZE_CLASSES = [
            "text-xs",
            "text-sm",
            "text-base",
            "text-lg",
            "text-xl",
            "text-2xl",
            "text-3xl",
            "text-4xl",
            "text-5xl",
            "text-6xl",
            "text-7xl",
            "text-8xl",
            "text-9xl",
        ]
        for m_cls in re.finditer(
            r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE
        ):
            cls = m_cls.group(1)
            found = [
                s
                for s in SIZE_CLASSES
                if re.search(r"(?<![a-z-])" + re.escape(s) + r"(?![a-zA-Z0-9-])", cls)
            ]
            if len(found) >= 2:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"{rule['description']} Found: {', '.join(found)}",
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "tailwind_weight_conflict":
        WEIGHT_CLASSES = [
            "font-thin",
            "font-extralight",
            "font-light",
            "font-normal",
            "font-medium",
            "font-semibold",
            "font-bold",
            "font-extrabold",
            "font-black",
        ]
        for m_cls in re.finditer(
            r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE
        ):
            cls = m_cls.group(1)
            found = [
                w
                for w in WEIGHT_CLASSES
                if re.search(r"(?<![a-z-])" + re.escape(w) + r"(?![a-zA-Z0-9-])", cls)
            ]
            if len(found) >= 2:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"{rule['description']} Found: {', '.join(found)}",
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "tailwind_display_conflict":
        DISPLAY_CLASSES = [
            "flex",
            "block",
            "inline-flex",
            "inline-block",
            "inline",
            "hidden",
            "grid",
            "contents",
        ]
        for m_cls in re.finditer(
            r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE
        ):
            cls = m_cls.group(1)
            found = [
                d
                for d in DISPLAY_CLASSES
                if re.search(r"(?<![a-z-])" + re.escape(d) + r"(?![a-zA-Z0-9-])", cls)
            ]
            # Conflict: flex+hidden, flex+block, etc.
            if (
                (
                    "hidden" in found
                    and ("flex" in found or "block" in found or "grid" in found)
                )
                or ("flex" in found and "block" in found)
                or ("grid" in found and "block" in found)
            ):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"{rule['description']} Found: {', '.join(found)}",
                        "command": rule["command"],
                    }
                )
                break
        return issues

    return None


def _analyze_html_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run HTML element and attribute heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "orphaned_label":
        for match in re.finditer(r"<label\b[^>]*>", content, re.IGNORECASE):
            tag = match.group(0)
            has_association = (
                re.search(r"\bhtmlFor\s*=", tag) is not None
                if ext in {".jsx", ".tsx"}
                else re.search(r"\bfor\s*=", tag, re.IGNORECASE) is not None
            )
            if not has_association:
                issues.append(_issue_for_match(rule, filepath, content, match))
                break
        return issues

    if custom == "round_number_metric":
        pattern = rule.get("pattern")
        if not isinstance(pattern, re.Pattern):
            return issues
        for match in pattern.finditer(content):
            if _is_visible_markup_text(content, match.start(), match.end()):
                issues.append(_issue_for_match(rule, filepath, content, match))
                break
        return issues

    if custom == "img_missing_dimensions":
        for m_img in re.finditer(r"<img\b[^>]*>", content, re.IGNORECASE):
            img_tag = m_img.group(0)
            has_width = re.search(r"\bwidth=", img_tag, re.IGNORECASE)
            has_height = re.search(r"\bheight=", img_tag, re.IGNORECASE)
            if not (has_width and has_height):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "missing_tabular_nums":
        if re.search(r"<table\b", content, re.IGNORECASE) and not re.search(
            r"tabular-nums", content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "placeholder_only_input":
        for m_inp in re.finditer(r"<input\b[^>]*>", content, re.IGNORECASE):
            tag = m_inp.group(0)
            if re.search(r"\bplaceholder=", tag, re.IGNORECASE):
                has_id = re.search(r"\bid=", tag, re.IGNORECASE)
                has_label = re.search(r"\baria-label(?:ledby)?=", tag, re.IGNORECASE)
                if not (has_id or has_label):
                    issues.append(
                        {
                            "id": rule["id"],
                            "file": str(filepath.resolve()),
                            "tier": rule["tier"],
                            "issue": rule["description"],
                            "command": rule["command"],
                        }
                    )
                    break
        return issues

    if custom == "srcset_missing":
        if re.search(r"<img\b", content, re.IGNORECASE) and not re.search(
            r"\bsrcset=|\bsrcSet=", content
        ):
            # Skip if all img tags use data URIs or Next.js Image component is used
            img_tags = re.findall(r"<img\b[^>]*>", content, re.IGNORECASE)
            non_data_imgs = [
                t
                for t in img_tags
                if not re.search(r'src=["\']data:', t, re.IGNORECASE)
            ]
            if non_data_imgs:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "anchor_target_blank":
        if re.search(r'target=["\']_blank["\']', content, re.IGNORECASE):
            if not re.search(r"noopener", content, re.IGNORECASE) or not re.search(
                r"noreferrer", content, re.IGNORECASE
            ):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    return None


def _analyze_browser_security_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run browser security and SSR-safety heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "dangerous_html":
        if re.search(r"dangerouslySetInnerHTML", content) and not re.search(
            r"DOMPurify", content
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "document_cookie_ssr":
        if re.search(r"\bdocument\.cookie\b", content) and not re.search(
            r"typeof\s+(?:window|document)\s*!==", content
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "inner_html_assign":
        if re.search(r"\.innerHTML\s*[+]?=\s*", content) and not re.search(
            r"DOMPurify", content
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "navigator_ssr":
        if re.search(r"\bnavigator\.\w+", content) and not re.search(
            r"typeof\s+window\s*!==", content
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "postmessage_origin_missing":
        if re.search(
            r"addEventListener\s*\(\s*['\"]message['\"]", content
        ) and not re.search(r"event\.origin|e\.origin", content):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "localstorage_ssr":
        if re.search(r"\b(?:localStorage|sessionStorage)\b", content):
            if not re.search(r'typeof\s+window\s*!==\s*["\']undefined["\']', content):
                # Don't flag if it's inside a useEffect (client-only)
                in_use_effect = bool(
                    re.search(
                        r"useEffect\s*\(\s*(?:\(\s*\)|[^,)]+)\s*=>\s*\{[^}]*(?:localStorage|sessionStorage)",
                        content,
                        re.DOTALL,
                    )
                )
                if not in_use_effect:
                    issues.append(
                        {
                            "id": rule["id"],
                            "file": str(filepath.resolve()),
                            "tier": rule["tier"],
                            "issue": rule["description"],
                            "command": rule["command"],
                        }
                    )
        return issues

    if custom == "window_object_ssr":
        if re.search(r"\bwindow\.\w+", content):
            if not re.search(r'typeof\s+window\s*!==\s*["\']undefined["\']', content):
                in_use_effect = bool(
                    re.search(
                        r"useEffect\s*\(\s*(?:\(\s*\)|[^,)]+)\s*=>\s*\{[^}]*window\.",
                        content,
                        re.DOTALL,
                    )
                )
                if not in_use_effect:
                    issues.append(
                        {
                            "id": rule["id"],
                            "file": str(filepath.resolve()),
                            "tier": rule["tier"],
                            "issue": rule["description"],
                            "command": rule["command"],
                        }
                    )
        return issues

    return None


def _analyze_react_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run React composition and dependency heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "duplicate_import":
        import_modules: list[str] = []
        for m_imp in re.finditer(
            r"import\s+[^;]+\s+from\s+['\"]([^'\"]+)['\"]", content
        ):
            mod = m_imp.group(1)
            if mod in import_modules:
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"{rule['description']} Module: '{mod}'",
                        "command": rule["command"],
                    }
                )
                break
            import_modules.append(mod)
        return issues

    if custom == "missing_key_prop":
        # .map() that returns JSX but none of the returned elements have key=
        for m_map in re.finditer(r"\.map\s*\(", content):
            start = m_map.end()
            # Grab up to 500 chars of context
            chunk = content[start : start + 500]
            if re.search(r"<[A-Z][a-zA-Z]*\b|<[a-z][a-z-]+\b", chunk) and not re.search(
                r"\bkey=", chunk
            ):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "framer_no_reduced_motion":
        if re.search(r"from ['\"]framer-motion['\"]", content) and re.search(
            r"\bmotion\.", content
        ):
            if not re.search(r"useReducedMotion", content):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "lazy_without_suspense":
        if re.search(r"(?:React\.)?lazy\s*\(", content) and not re.search(
            r"Suspense", content
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    return None


def _analyze_control_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run interactive-control accessibility heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "media_autoplay":
        for m_av in re.finditer(r"<(?:video|audio)\b([^>]*)", content, re.IGNORECASE):
            attrs = m_av.group(1)
            if re.search(
                r"\bautoPlay\b|\bautoplay\b", attrs, re.IGNORECASE
            ) and not re.search(r"\bmuted\b", attrs, re.IGNORECASE):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "select_no_label":
        for m_sel in re.finditer(r"<select\b([^>]*)", content, re.IGNORECASE):
            attrs = m_sel.group(1)
            # Check nearby (within 200 chars) for a label
            pos = m_sel.start()
            context = content[max(0, pos - 200) : pos + 200]
            if not re.search(
                r"<label\b|aria-label=|aria-labelledby=", context, re.IGNORECASE
            ):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "icon_aria_missing":
        for m_icon in re.finditer(
            r"<svg\b[^>]*>|<i\s+class=[^>]+>", content, re.IGNORECASE
        ):
            pos = m_icon.start()
            context = content[max(0, pos - 100) : pos + 200]
            if not re.search(
                r"aria-(?:label|hidden|labelledby)=", context, re.IGNORECASE
            ):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "icon_only_button":
        for m_btn in re.finditer(
            r"<button\b([^>]*)>\s*<(?:svg|i)\b", content, re.IGNORECASE
        ):
            attrs = m_btn.group(1)
            if not re.search(r"aria-label=", attrs, re.IGNORECASE):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    if custom == "modal_no_aria":
        if re.search(r"(?:modal|Modal)", content) and not re.search(
            r'role=["\']dialog["\']', content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "missing_aria_role":
        for m_el in re.finditer(
            r"<(?:div|span)\s[^>]*on(?:Click|Keydown|Keyup)[^>]*>",
            content,
            re.IGNORECASE,
        ):
            if not re.search(r"\brole=", m_el.group(0), re.IGNORECASE):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
                break
        return issues

    return None


def _analyze_runtime_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run React runtime-state heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "next_image_raw":
        if re.search(r"from ['\"]next/", content) and re.search(
            r"<img\b", content, re.IGNORECASE
        ):
            if not re.search(r"from ['\"]next/image['\"]", content):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "missing_loading_state":
        if re.search(r"\buseQuery\b", content) and not re.search(
            r"\bisLoading\b", content
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "missing_error_state":
        if re.search(r"\buseQuery\b", content) and re.search(r"\bisLoading\b", content):
            if not re.search(r"\bisError\b|\berror\b", content):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    return None


def _analyze_design_pattern_custom_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    dynamic_colors: dict[str, str] | None,
) -> list[dict] | None:
    """Run repeated design-pattern heuristics."""
    issues = []
    custom = rule.get("_custom_check")
    if custom == "three_equal_column":
        if re.search(r"grid-cols-3\b", content, re.IGNORECASE):
            # Flag if there are 3+ child elements with identical classNames (crude check)
            child_classes = re.findall(r'className=["\']([^"\']+)["\']', content)
            if len(child_classes) >= 3:
                from collections import Counter

                cls_counts = Counter(child_classes)
                if cls_counts.most_common(1)[0][1] >= 3:
                    issues.append(
                        {
                            "id": rule["id"],
                            "file": str(filepath.resolve()),
                            "tier": rule["tier"],
                            "issue": rule["description"],
                            "command": rule["command"],
                        }
                    )
        return issues

    if custom == "font_weight_extremes":
        if re.search(r"\bfont-bold\b", content) and re.search(
            r"\bfont-normal\b", content
        ):
            if not re.search(r"\bfont-medium\b|\bfont-semibold\b", content):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "accordion_faq":
        if re.search(r"\bAccordion\b", content, re.IGNORECASE) and re.search(
            r"\bFAQ\b", content, re.IGNORECASE
        ):
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    if custom == "dark_mode_toggle":
        if re.search(
            r"(?:ThemeToggle|toggleDarkMode|DarkModeToggle|darkMode)",
            content,
            re.IGNORECASE,
        ):
            if not re.search(r"prefers-color-scheme", content, re.IGNORECASE):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "hardcoded_copyright_year":
        if re.search(r"©\s*20\d{2}|&copy;\s*20\d{2}", content, re.IGNORECASE):
            if not re.search(r"getFullYear\s*\(\s*\)", content):
                issues.append(
                    {
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": rule["description"],
                        "command": rule["command"],
                    }
                )
        return issues

    if custom == "pricing_table":
        PRICING_KW = ["Free", "Pro", "Enterprise", "Starter", "Basic", "Premium"]
        count = sum(
            1
            for kw in PRICING_KW
            if re.search(r"\b" + kw + r"\b", content, re.IGNORECASE)
        )
        if count >= 3:
            issues.append(
                {
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"],
                }
            )
        return issues

    return None


_CUSTOM_CHECK_HANDLERS = {
    "div_soup": _analyze_document_structure_custom_rule,
    "missing_hover": _analyze_interaction_custom_rule,
    "missing_focus": _analyze_interaction_custom_rule,
    "missing_transition": _analyze_interaction_custom_rule,
    "ugly_scrollbar": _analyze_interaction_custom_rule,
    "nested_ternary": _analyze_document_structure_custom_rule,
    "disabled_cursor": _analyze_interaction_custom_rule,
    "commented_code": _analyze_commented_code_custom_rule,
    "contrast_ratio": _analyze_contrast_custom_rule,
    "unused_import": _analyze_unused_import_custom_rule,
    "unused_state": _analyze_unused_state_custom_rule,
    "video_no_captions": _analyze_accessibility_custom_rule,
    "focus_outline_removed": _analyze_accessibility_custom_rule,
    "focus_visible_missing": _analyze_accessibility_custom_rule,
    "important_abuse": _analyze_css_custom_rule,
    "important_animation": _analyze_css_custom_rule,
    "css_scroll_behavior": _analyze_css_custom_rule,
    "sticky_without_top": _analyze_css_custom_rule,
    "scroll_snap_without_behavior": _analyze_css_custom_rule,
    "generic_font_family": _analyze_css_custom_rule,
    "font_display_missing": _analyze_css_custom_rule,
    "alpha_color_abuse": _analyze_css_custom_rule,
    "grid_auto_fit_missing": _analyze_css_custom_rule,
    "scroll_smooth_no_motion": _analyze_css_custom_rule,
    "no_select_content": _analyze_accessibility_custom_rule,
    "outline_none": _analyze_accessibility_custom_rule,
    "reduced_motion_missing": _analyze_accessibility_custom_rule,
    "tailwind_font_conflict": _analyze_tailwind_custom_rule,
    "tailwind_weight_conflict": _analyze_tailwind_custom_rule,
    "tailwind_display_conflict": _analyze_tailwind_custom_rule,
    "missing_meta_description": _analyze_accessibility_custom_rule,
    "skip_to_content_missing": _analyze_accessibility_custom_rule,
    "missing_favicon": _analyze_accessibility_custom_rule,
    "img_missing_dimensions": _analyze_html_custom_rule,
    "orphaned_label": _analyze_html_custom_rule,
    "missing_tabular_nums": _analyze_html_custom_rule,
    "placeholder_only_input": _analyze_html_custom_rule,
    "srcset_missing": _analyze_html_custom_rule,
    "anchor_target_blank": _analyze_html_custom_rule,
    "round_number_metric": _analyze_html_custom_rule,
    "dangerous_html": _analyze_browser_security_custom_rule,
    "duplicate_import": _analyze_react_custom_rule,
    "document_cookie_ssr": _analyze_browser_security_custom_rule,
    "inner_html_assign": _analyze_browser_security_custom_rule,
    "navigator_ssr": _analyze_browser_security_custom_rule,
    "postmessage_origin_missing": _analyze_browser_security_custom_rule,
    "localstorage_ssr": _analyze_browser_security_custom_rule,
    "window_object_ssr": _analyze_browser_security_custom_rule,
    "missing_key_prop": _analyze_react_custom_rule,
    "framer_no_reduced_motion": _analyze_react_custom_rule,
    "lazy_without_suspense": _analyze_react_custom_rule,
    "media_autoplay": _analyze_control_custom_rule,
    "select_no_label": _analyze_control_custom_rule,
    "icon_aria_missing": _analyze_control_custom_rule,
    "icon_only_button": _analyze_control_custom_rule,
    "next_image_raw": _analyze_runtime_custom_rule,
    "three_equal_column": _analyze_design_pattern_custom_rule,
    "font_weight_extremes": _analyze_design_pattern_custom_rule,
    "missing_loading_state": _analyze_runtime_custom_rule,
    "missing_error_state": _analyze_runtime_custom_rule,
    "accordion_faq": _analyze_design_pattern_custom_rule,
    "dark_mode_toggle": _analyze_runtime_custom_rule,
    "hardcoded_copyright_year": _analyze_design_pattern_custom_rule,
    "modal_no_aria": _analyze_control_custom_rule,
    "pricing_table": _analyze_design_pattern_custom_rule,
    "missing_aria_role": _analyze_control_custom_rule,
}
