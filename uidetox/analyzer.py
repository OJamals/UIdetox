"""Static Slop Analyzer: Detects AI anti-patterns via regex/AST rules."""

import re
from pathlib import Path

from uidetox.fileset import IGNORED_DIRECTORY_NAMES, ProjectFileSet, find_project_root

# Directories to always skip during traversal
IGNORE_DIRS = IGNORED_DIRECTORY_NAMES

HAS_AST = False
try:
    import tree_sitter
    import tree_sitter_javascript as ts_js
    import tree_sitter_typescript as ts_ts
    import tree_sitter_css as ts_css
    HAS_AST = True
    JS_LANG = tree_sitter.Language(ts_js.language())
    TSX_LANG = tree_sitter.Language(ts_ts.language_tsx())
    CSS_LANG = tree_sitter.Language(ts_css.language())
except ImportError:
    pass

from uidetox.analyzer_rules import RULES, _ALL_FE_EXTS, _FE_EXTS, _JSX_EXTS

_USESTATE_BINDING_RE = re.compile(
    r"\b(?:const|let|var)\s+\[\s*(?P<state>[A-Za-z_$][\w$]*)\s*,"
    r"\s*[A-Za-z_$][\w$]*\s*\]\s*=\s*(?:React\.)?useState\b"
)
_IDENTIFIER_TOKEN_RE = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[A-Z]+|[0-9]+"
)
_ANIMATION_STATE_TOKENS = frozenset({
    "x", "y", "top", "left", "right", "bottom", "opacity", "scale",
    "rotate", "position", "transform",
})
_ANIMATION_STATE_PREFIXES = ("animat", "transit", "translate")


def _extract_usestate_binding(declaration_text: str) -> str | None:
    """Return the first state binding from a standard destructured useState declaration."""
    match = _USESTATE_BINDING_RE.search(declaration_text)
    return match.group("state") if match else None


def _identifier_tokens(identifier: str) -> tuple[str, ...]:
    """Split an identifier across separators, digits, and camel/Pascal case."""
    return tuple(token.lower() for token in _IDENTIFIER_TOKEN_RE.findall(identifier))


def _is_animation_state_identifier(identifier: str) -> bool:
    """Classify animation state from identifier tokens, never raw substrings."""
    return any(
        token in _ANIMATION_STATE_TOKENS
        or token.startswith(_ANIMATION_STATE_PREFIXES)
        for token in _identifier_tokens(identifier)
    )

def _get_parser(ext: str):
    if not HAS_AST:
        return None
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return tree_sitter.Parser(JS_LANG)
    elif ext in {".ts", ".tsx"}:
        return tree_sitter.Parser(TSX_LANG)
    elif ext in {".css", ".scss", ".less"}:
        return tree_sitter.Parser(CSS_LANG)
    return None

def _analyze_ast(filepath: Path, content: str, ext: str) -> list[dict]:
    parser = _get_parser(ext)
    if not parser:
        return []

    try:
        tree = parser.parse(content.encode("utf-8", errors="ignore"))
    except Exception:
        return []

    issues = []
    fpath = str(filepath.resolve())

    if ext in {".tsx", ".jsx", ".js", ".ts"}:
        state = {
            "div_count": 0, "semantic_count": 0, "nested_ternaries": 0,
            "cards": 0, "charts": 0,
            # Deep prop drilling detection
            "prop_pass_depth": 0,  # max depth of a prop passed through components
            "prop_names_seen": {},  # prop name -> list of component names where it appears
            # useState for animation detection
            "usestate_for_animation": False,
            # Identical sibling components (e.g., 4 KPI cards in a row)
            "sibling_components": {},  # parent_id -> list of child component names
            # Styled-component nesting depth
            "styled_nesting_depth": 0,
        }

        def _node_text(node) -> str:
            try:
                return node.text.decode("utf-8", errors="ignore")
            except AttributeError:
                return str(node.text)

        def walk(node, depth=0):
            if node.type in ("jsx_element", "jsx_self_closing_element"):
                open_tag = node.child_by_field_name("open_tag") if node.type == "jsx_element" else node
                if open_tag:
                    name_node = open_tag.child_by_field_name("name")
                    if name_node:
                        tag_name = _node_text(name_node)

                        if tag_name == "div":
                            state["div_count"] += 1
                        elif tag_name in {"nav", "main", "article", "section", "aside", "header", "footer"}:
                            state["semantic_count"] += 1

                        # Detect Dashboard Slop
                        if "Card" in tag_name or "Stat" in tag_name or "Metric" in tag_name:
                            state["cards"] += 1
                        elif "Chart" in tag_name or "Graph" in tag_name or "Activity" in tag_name:
                            state["charts"] += 1

                        # Track sibling component repetition for layout-level slop
                        parent_id = id(node.parent) if node.parent else 0
                        if tag_name[0:1].isupper():  # React component (capitalized)
                            state["sibling_components"].setdefault(parent_id, []).append(tag_name)

                        # Detect deep prop drilling: props passed through with same name
                        for attr in (open_tag.children or []):
                            if attr.type == "jsx_attribute":
                                attr_name_node = attr.child_by_field_name("name")
                                if attr_name_node:
                                    attr_name = _node_text(attr_name_node)
                                    state["prop_names_seen"].setdefault(attr_name, set()).add(tag_name)

            elif node.type == "ternary_expression":
                for child in node.children:
                    if child.type == "ternary_expression":
                        state["nested_ternaries"] += 1

            # Detect useState used for animation values (bad pattern)
            elif node.type == "lexical_declaration":
                binding = _extract_usestate_binding(_node_text(node))
                if binding and _is_animation_state_identifier(binding):
                    state["usestate_for_animation"] = True

            # Detect deeply nested styled-components tagged templates
            elif node.type == "tagged_template_expression":
                tag = node.child_by_field_name("function")
                if tag:
                    tag_text = _node_text(tag)
                    if "styled" in tag_text or "css" in tag_text:
                        # Count nesting depth of CSS selectors within
                        tmpl = node.child_by_field_name("arguments") or node
                        nesting = _node_text(tmpl).count("{")
                        if nesting > state["styled_nesting_depth"]:
                            state["styled_nesting_depth"] = nesting

            for child in node.children:
                walk(child, depth + 1)

        walk(tree.root_node)

        if state["div_count"] > 20 and state["semantic_count"] == 0:
            issues.append({
                "id": "DIV_SOUP_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({state['div_count']} divs, 0 semantic elements)",
                "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>."
            })

        if state["nested_ternaries"] >= 2:
            issues.append({
                "id": "NESTED_TERNARY_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Nested ternary operator detected via AST — harms readability in JSX. ({state['nested_ternaries']} nested ternaries found)",
                "command": "Extract nested ternaries into named variables or early returns for clarity."
            })

        if state["cards"] >= 3 and state["charts"] >= 1:
            issues.append({
                "id": "HERO_DASHBOARD_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Hero metric dashboard pattern detected via AST ({state['cards']} cards, {state['charts']} charts) — cliché AI layout.",
                "command": "Replace with contextual data visualization or inline metrics woven into the narrative flow."
            })

        # ── AST: Deep prop drilling ──
        drilled_props = [
            name for name, components in state["prop_names_seen"].items()
            if len(components) >= 4 and name not in {"className", "children", "key", "id", "style", "ref", "onClick", "onChange"}
        ]
        if drilled_props:
            sample = ", ".join(sorted(drilled_props)[:5])
            issues.append({
                "id": "PROP_DRILLING_SLOP",
                "file": fpath,
                "tier": "T3",
                "issue": f"Deep prop drilling detected via AST — prop(s) '{sample}' passed through 4+ components.",
                "command": "Extract deeply drilled props into React Context, Zustand store, or composition pattern to reduce coupling."
            })

        # ── AST: useState for animation values ──
        if state["usestate_for_animation"]:
            issues.append({
                "id": "ANIMATE_STATE_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": "React useState used for animation values — causes re-renders on every frame.",
                "command": "Use CSS transitions/animations, Framer Motion, or useRef for animation state. Never drive 60fps animations through React state."
            })

        # ── AST: Identical sibling components (generic layout slop) ──
        for parent_id, children in state["sibling_components"].items():
            if len(children) >= 4:
                from collections import Counter
                counts = Counter(children)
                for comp_name, count in counts.items():
                    if count >= 4:
                        issues.append({
                            "id": "IDENTICAL_SIBLINGS_SLOP",
                            "file": fpath,
                            "tier": "T3",
                            "issue": f"Generic layout pattern detected via AST: {count} identical <{comp_name}/> siblings — dashboard/feature-grid slop.",
                            "command": f"Vary the {comp_name} instances (different sizes, spans, emphasis) or replace with asymmetric layout. Identical cards = AI fingerprint."
                        })
                        break  # One issue per parent

        # ── AST: Deeply nested styled-components ──
        if state["styled_nesting_depth"] >= 5:
            issues.append({
                "id": "STYLED_NESTING_SLOP",
                "file": fpath,
                "tier": "T2",
                "issue": f"Deeply nested styled-component selectors detected ({state['styled_nesting_depth']} levels) — specificity war.",
                "command": "Flatten CSS nesting. Use component composition instead of deeply nested selectors."
            })

    return issues


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
        r'(?:<(?:\w+Card|\w+Stat|\w+Metric|\w+KPI)\b[^>]*>)',
        content, re.IGNORECASE
    )
    chart_patterns = re.findall(
        r'(?:<(?:\w*Chart|\w*Graph|LineChart|BarChart|PieChart|AreaChart|ResponsiveContainer)\b)',
        content, re.IGNORECASE
    )
    if len(card_patterns) >= 4 and len(chart_patterns) >= 1:
        issues.append({
            "id": "DASHBOARD_LAYOUT_SLOP",
            "file": fpath,
            "tier": "T3",
            "issue": f"Generic dashboard layout: {len(card_patterns)} KPI/stat cards + {len(chart_patterns)} chart(s) — classic AI dashboard slop.",
            "command": "Replace identical card grid with varied sizes (span-2 hero metric, inline sparklines). Weave data into contextual narrative."
        })

    # ── Heuristic 2: Feature Grid Slop (identical feature items) ──
    # Detect 3+ identical JSX blocks with icon + heading + description pattern
    feature_block = re.findall(
        r'(?:<(?:div|section|article|li)\s[^>]*>[\s\S]{30,300}?'
        r'(?:<\w+Icon|<Icon\b|icon=|<svg\b)[\s\S]{10,200}?'
        r'(?:<h[23456]|<(?:Title|Heading|CardTitle))'
        r'[\s\S]{10,200}?'
        r'(?:<p\b|<(?:Description|Text|CardDescription))'
        r')',
        content, re.IGNORECASE
    )
    if len(feature_block) >= 3:
        issues.append({
            "id": "FEATURE_GRID_SLOP",
            "file": fpath,
            "tier": "T3",
            "issue": f"Feature grid slop: {len(feature_block)} identical icon+heading+description blocks — generic SaaS landing pattern.",
            "command": "Vary feature presentations (alternate image/text, use different card sizes, stagger layouts). Break the 3-column monotony."
        })

    # ── Heuristic 3: Pricing Table Cliché ──
    pricing_signals = len(re.findall(r'(?:\$\d+|/mo(?:nth)?|/yr|/year|popular|recommended|enterprise|pro|starter|basic|premium)', content, re.IGNORECASE))
    pricing_cards = len(re.findall(r'(?:PricingCard|PricingTier|PricingPlan|price-card)', content, re.IGNORECASE))
    if pricing_signals >= 6 or pricing_cards >= 3:
        issues.append({
            "id": "PRICING_TABLE_SLOP",
            "file": fpath,
            "tier": "T3",
            "issue": "Pricing table cliché detected — 3-column pricing grid with 'Popular' badge is the #1 AI SaaS template.",
            "command": "Design pricing as a comparison flow, slider, or interactive calculator. Vary card sizes. Make the recommended plan visually dominant, not just badged."
        })

    # ── Heuristic 4: Zero Interactivity File ──
    has_interactivity = bool(re.search(
        r'(?:onClick|onChange|onSubmit|onPress|onFocus|onBlur|onKeyDown|onMouseEnter|onHover|hover:|focus:|active:|useState|useReducer|motion\.|animate)',
        content
    ))
    jsx_count = len(re.findall(r'<[A-Z]\w+', content))
    if not has_interactivity and jsx_count >= 5 and file_len > 50:
        issues.append({
            "id": "STATIC_COMPONENT_SLOP",
            "file": fpath,
            "tier": "T2",
            "issue": f"Static component detected: {jsx_count} JSX elements but zero interactivity (no handlers, no hover/focus, no animation).",
            "command": "Add hover states, transitions, or micro-interactions. Static pages feel dead — every component should respond to user input."
        })

    # ── Heuristic 5: Hero Section Heavy Page ──
    hero_count = len(re.findall(r'(?:hero|Hero|HERO)', content))
    section_count = len(re.findall(r'<(?:section|Section)\b', content, re.IGNORECASE))
    if hero_count >= 2 and section_count <= 3:
        issues.append({
            "id": "HERO_HEAVY_SLOP",
            "file": fpath,
            "tier": "T2",
            "issue": "Hero-section-heavy page — multiple hero blocks without enough content sections.",
            "command": "A page needs one hero at most. Replace additional heroes with content sections, testimonials, or data-driven blocks."
        })

    # ── Heuristic 6: Testimonial Grid Slop ──
    testimonial_signals = len(re.findall(
        r'(?:testimonial|review|quote|avatar.*?(?:name|title)|rating|stars?.*?(?:5|five))',
        content, re.IGNORECASE
    ))
    if testimonial_signals >= 6:
        issues.append({
            "id": "TESTIMONIAL_GRID_SLOP",
            "file": fpath,
            "tier": "T2",
            "issue": "Generic testimonial grid detected — avatar + quote + name pattern repeated.",
            "command": "Use varied testimonial layouts: full-width quotes, video testimonials, inline social proof, or rotating carousel with real data."
        })

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
        if HAS_AST and ext in {".tsx", ".jsx", ".js", ".ts"}:
            return issues # Handled by AST
        div_count = len(re.findall(r'<div[\s>]', content, re.IGNORECASE))
        semantic_count = len(re.findall(
            r'<(?:nav|main|article|section|aside|header|footer)[\s>]',
            content, re.IGNORECASE
        ))
        if div_count > 20 and semantic_count == 0:
            issues.append({
                "id": rule["id"],
                "file": str(filepath.resolve()),
                "tier": rule["tier"],
                "issue": f"{rule['description']} ({div_count} divs, 0 semantic elements)",
                "command": rule["command"]
            })
        return issues

    # Custom check: missing_hover — buttons with className but no hover: class

    if custom == "nested_ternary":
        if HAS_AST and ext in {".tsx", ".jsx", ".js", ".ts"}:
            return issues # Handled by AST
        # Count nested ternaries: lines with ? ... ? ... : pattern
        ternary_nests = len(re.findall(r'\?[^:?\n]{0,80}\?', content))
        if ternary_nests >= 2:
            issues.append({
                "id": rule["id"],
                "file": str(filepath.resolve()),
                "tier": rule["tier"],
                "issue": f"{rule['description']} ({ternary_nests} nested ternaries found)",
                "command": rule["command"]
            })
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
        for m in re.finditer(r'<button[^>]*className=["\']([^"\']*)["\']', content, re.IGNORECASE):
            classes = m.group(1)
            if "hover:" not in classes:
                issues.append({
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"]
                })
                break  # Flag once per file
        return issues

    # Custom check: missing_focus — interactive elements without focus: class
    if custom == "missing_focus":
        for m in re.finditer(r'<(?:button|a)\s[^>]*className=["\']([^"\']*)["\']', content, re.IGNORECASE):
            classes = m.group(1)
            if "focus:" not in classes:
                issues.append({
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"]
                })
                break  # Flag once per file
        return issues

    # Custom check: missing_transition — hover: classes without transition-
    if custom == "missing_transition":
        for m in re.finditer(r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE):
            classes = m.group(1)
            if "hover:" in classes and "transition" not in classes:
                issues.append({
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"]
                })
                break  # Flag once per file
        return issues

    # Custom check: ugly_scrollbar — overflow scroll without scrollbar styling
    if custom == "ugly_scrollbar":
        for m in re.finditer(r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE):
            classes = m.group(1)
            if re.search(r'overflow-[xy]-(?:auto|scroll)', classes) and "scrollbar" not in classes:
                issues.append({
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"]
                })
                break  # Flag once per file
        return issues

    # Custom check: nested_ternary — only flag in JSX return blocks (rough heuristic)

    if custom == "disabled_cursor":
        # Find elements with disabled prop/attr
        disabled_elements = re.findall(
            r'(?:disabled|isDisabled)[^>]*class(?:Name)?=["\']([^"\']*)["\']',
            content, re.IGNORECASE
        )
        for classes in disabled_elements:
            if "cursor-not-allowed" not in classes and "disabled:" not in classes:
                issues.append({
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": rule["description"],
                    "command": rule["command"]
                })
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
                r'^(?://|/\*|\*|{/\*)\s*(?:'
                r'<[A-Z]|'
                r'(?:const|let|var|function|import|export|return|if|for|while)\s|'
                r'(?:className|onClick|onChange|style)=|'
                r'\w+\.\w+\(|'
                r'\}\s*(?:else|catch|finally)|'
                r'(?:await|async)\s'
                r')',
                stripped,
            ):
                commented_code_lines += 1
        if commented_code_lines >= 3:
            issues.append({
                "id": rule["id"],
                "file": str(filepath.resolve()),
                "tier": rule["tier"],
                "issue": f"{rule['description']} ({commented_code_lines} lines of commented-out code)",
                "command": rule["command"]
            })
        return issues

    # Custom check: unused_import — imports whose identifiers appear nowhere else in the file

    return None


_IMPORT_PATTERN = re.compile(
    r'^import\s+'
    r'(?:'
    r'(?:type\s+)?(\w+)(?:\s*,\s*\{([^}]+)\})?'  # default + named
    r'|\{([^}]+)\}'                                 # named only
    r'|\*\s+as\s+(\w+)'                             # namespace
    r')'
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
            occurrences = len(re.findall(r'\b' + re.escape(name) + r'\b', content))
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
        issues.append({
            "id": rule["id"],
            "file": str(filepath.resolve()),
            "tier": rule["tier"],
            "issue": f"{rule['description']} Likely unused: {sample}{suffix}",
            "command": rule["command"]
        })
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
        for m in re.finditer(r'const\s+\[(\w+),\s*set(\w+)\]\s*=\s*useState', content):
            state_var = m.group(1)
            # Check if state var is referenced beyond the declaration
            occurrences = len(re.findall(r'\b' + re.escape(state_var) + r'\b', content))
            if occurrences <= 1:
                issues.append({
                    "id": rule["id"],
                    "file": str(filepath.resolve()),
                    "tier": rule["tier"],
                    "issue": f"{rule['description']} `{state_var}` appears unused.",
                    "command": rule["command"]
                })
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
        for m in re.finditer(r'class(?:Name)?=["\']([^"\']*)["\']', content, re.IGNORECASE):
            classes = m.group(1).split()
            bg_color = None
            text_color = None

            for c in classes:
                if c.startswith("bg-"):
                    bg_name = c[3:].split('/')[0]
                    if bg_name in dynamic_colors:
                        bg_color = dynamic_colors[bg_name]
                elif c.startswith("text-"):
                    text_name = c[5:].split('/')[0]
                    if text_name in dynamic_colors:
                        text_color = dynamic_colors[text_name]

            if bg_color and text_color:
                from uidetox.color_utils import contrast_ratio
                ratio = contrast_ratio(text_color, bg_color)
                if ratio < 4.5:
                    issues.append({
                        "id": rule["id"],
                        "file": str(filepath.resolve()),
                        "tier": rule["tier"],
                        "issue": f"Low contrast detected: {text_color} on {bg_color} (ratio {ratio:.1f}:1).",
                        "command": rule["command"]
                    })
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
        if re.search(r'<video\b', content, re.IGNORECASE) and not re.search(r'<track\b', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "focus_outline_removed":
        # :focus { outline: none } or :focus { outline: 0 }
        if re.search(r':focus\s*\{[^}]*outline:\s*(?:none|0)\b', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "focus_visible_missing":
        if re.search(r':focus\s*\{', content, re.IGNORECASE) and not re.search(r':focus-visible\s*\{', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "no_select_content":
        if re.search(r'\bselect-none\b', content):
            # Flag if used on non-button elements (not inside <button>)
            # Simple heuristic: flag if it appears in className on a non-button
            if re.search(r'<(?!button)(?:[a-z][a-z0-9]*)(?:\s[^>]*)?\bclassName=[^>]*select-none', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "outline_none":
        for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']*outline-none[^"\']*)["\']', content, re.IGNORECASE):
            cls = m_cls.group(1)
            if 'focus-visible:' not in cls and 'focus:ring' not in cls:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "reduced_motion_missing":
        for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']*animate-[^"\']*)["\']', content, re.IGNORECASE):
            cls = m_cls.group(1)
            if 'motion-reduce:' not in cls:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "missing_meta_description":
        if re.search(r'<head\b', content, re.IGNORECASE) and not re.search(r'<meta\s[^>]*name=["\']description["\']', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "skip_to_content_missing":
        if re.search(r'<nav\b', content, re.IGNORECASE) and re.search(r'<main\b', content, re.IGNORECASE):
            if not re.search(r'href=["\']#', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "missing_favicon":
        if re.search(r'<head\b', content, re.IGNORECASE) and not re.search(r'rel=["\'](?:shortcut icon|icon)["\']', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
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
    if custom == "css_scroll_behavior":
        if re.search(r'scroll-behavior:\s*smooth', content, re.IGNORECASE) and not re.search(r'prefers-reduced-motion', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "sticky_without_top":
        for block_m in re.finditer(r'position:\s*sticky[^}]*', content, re.IGNORECASE | re.DOTALL):
            block = block_m.group(0)
            if not re.search(r'\btop\s*:', block, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "scroll_snap_without_behavior":
        if re.search(r'scroll-snap-type:', content, re.IGNORECASE) and not re.search(r'scroll-behavior:', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "generic_font_family":
        AI_FONTS = re.compile(r"font-family:\s*(?:'Inter'|Inter|'Roboto'|Roboto|'Open Sans'|Open Sans|'Montserrat'|Montserrat|'Poppins'|Poppins|'Lato'|Lato)", re.IGNORECASE)
        if AI_FONTS.search(content) and not re.search(r'-apple-system', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "font_display_missing":
        for ff_m in re.finditer(r'@font-face\s*\{([^}]*)\}', content, re.IGNORECASE | re.DOTALL):
            if 'font-display' not in ff_m.group(1):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "alpha_color_abuse":
        count = len(re.findall(r'(?:rgba|hsla)\s*\(', content, re.IGNORECASE))
        if count >= 5:
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": f"{rule['description']} ({count} instances found)", "command": rule["command"]})
        return issues

    if custom == "grid_auto_fit_missing":
        if re.search(r'grid-template-columns:\s*repeat\(\s*(?:[2-9]|\d{2,})\s*,', content, re.IGNORECASE):
            if not re.search(r'auto-fit|auto-fill', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "scroll_smooth_no_motion":
        if re.search(r'\bscroll-smooth\b', content) and not re.search(r'motion-reduce:scroll-auto', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
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
        SIZE_CLASSES = ['text-xs', 'text-sm', 'text-base', 'text-lg', 'text-xl',
                        'text-2xl', 'text-3xl', 'text-4xl', 'text-5xl', 'text-6xl', 'text-7xl', 'text-8xl', 'text-9xl']
        for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE):
            cls = m_cls.group(1)
            found = [s for s in SIZE_CLASSES if re.search(r'(?<![a-z-])' + re.escape(s) + r'(?![a-zA-Z0-9-])', cls)]
            if len(found) >= 2:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": f"{rule['description']} Found: {', '.join(found)}", "command": rule["command"]})
                break
        return issues

    if custom == "tailwind_weight_conflict":
        WEIGHT_CLASSES = ['font-thin', 'font-extralight', 'font-light', 'font-normal',
                           'font-medium', 'font-semibold', 'font-bold', 'font-extrabold', 'font-black']
        for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE):
            cls = m_cls.group(1)
            found = [w for w in WEIGHT_CLASSES if re.search(r'(?<![a-z-])' + re.escape(w) + r'(?![a-zA-Z0-9-])', cls)]
            if len(found) >= 2:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": f"{rule['description']} Found: {', '.join(found)}", "command": rule["command"]})
                break
        return issues

    if custom == "tailwind_display_conflict":
        DISPLAY_CLASSES = ['flex', 'block', 'inline-flex', 'inline-block', 'inline', 'hidden', 'grid', 'contents']
        for m_cls in re.finditer(r'class(?:Name)?=["\']([^"\']+)["\']', content, re.IGNORECASE):
            cls = m_cls.group(1)
            found = [d for d in DISPLAY_CLASSES if re.search(r'(?<![a-z-])' + re.escape(d) + r'(?![a-zA-Z0-9-])', cls)]
            # Conflict: flex+hidden, flex+block, etc.
            if ('hidden' in found and ('flex' in found or 'block' in found or 'grid' in found)) or \
               ('flex' in found and 'block' in found) or \
               ('grid' in found and 'block' in found):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": f"{rule['description']} Found: {', '.join(found)}", "command": rule["command"]})
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
    if custom == "img_missing_dimensions":
        for m_img in re.finditer(r'<img\b[^>]*>', content, re.IGNORECASE):
            img_tag = m_img.group(0)
            has_width = re.search(r'\bwidth=', img_tag, re.IGNORECASE)
            has_height = re.search(r'\bheight=', img_tag, re.IGNORECASE)
            if not (has_width and has_height):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "missing_tabular_nums":
        if re.search(r'<table\b', content, re.IGNORECASE) and not re.search(r'tabular-nums', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "placeholder_only_input":
        for m_inp in re.finditer(r'<input\b[^>]*>', content, re.IGNORECASE):
            tag = m_inp.group(0)
            if re.search(r'\bplaceholder=', tag, re.IGNORECASE):
                has_id = re.search(r'\bid=', tag, re.IGNORECASE)
                has_label = re.search(r'\baria-label(?:ledby)?=', tag, re.IGNORECASE)
                if not (has_id or has_label):
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
                    break
        return issues

    if custom == "srcset_missing":
        if re.search(r'<img\b', content, re.IGNORECASE) and not re.search(r'\bsrcset=|\bsrcSet=', content):
            # Skip if all img tags use data URIs or Next.js Image component is used
            img_tags = re.findall(r'<img\b[^>]*>', content, re.IGNORECASE)
            non_data_imgs = [t for t in img_tags if not re.search(r'src=["\']data:', t, re.IGNORECASE)]
            if non_data_imgs:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "anchor_target_blank":
        if re.search(r'target=["\']_blank["\']', content, re.IGNORECASE):
            if not re.search(r'noopener', content, re.IGNORECASE) or not re.search(r'noreferrer', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
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
        if re.search(r'dangerouslySetInnerHTML', content) and not re.search(r'DOMPurify', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "document_cookie_ssr":
        if re.search(r'\bdocument\.cookie\b', content) and not re.search(r'typeof\s+(?:window|document)\s*!==', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "inner_html_assign":
        if re.search(r'\.innerHTML\s*[+]?=\s*', content) and not re.search(r'DOMPurify', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "navigator_ssr":
        if re.search(r'\bnavigator\.\w+', content) and not re.search(r'typeof\s+window\s*!==', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "postmessage_origin_missing":
        if re.search(r"addEventListener\s*\(\s*['\"]message['\"]", content) and not re.search(r'event\.origin|e\.origin', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "localstorage_ssr":
        if re.search(r'\b(?:localStorage|sessionStorage)\b', content):
            if not re.search(r'typeof\s+window\s*!==\s*["\']undefined["\']', content):
                # Don't flag if it's inside a useEffect (client-only)
                in_use_effect = bool(re.search(r'useEffect\s*\(\s*(?:\(\s*\)|[^,)]+)\s*=>\s*\{[^}]*(?:localStorage|sessionStorage)', content, re.DOTALL))
                if not in_use_effect:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "window_object_ssr":
        if re.search(r'\bwindow\.\w+', content):
            if not re.search(r'typeof\s+window\s*!==\s*["\']undefined["\']', content):
                in_use_effect = bool(re.search(r'useEffect\s*\(\s*(?:\(\s*\)|[^,)]+)\s*=>\s*\{[^}]*window\.', content, re.DOTALL))
                if not in_use_effect:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
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
        for m_imp in re.finditer(r"import\s+[^;]+\s+from\s+['\"]([^'\"]+)['\"]", content):
            mod = m_imp.group(1)
            if mod in import_modules:
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": f"{rule['description']} Module: '{mod}'", "command": rule["command"]})
                break
            import_modules.append(mod)
        return issues

    if custom == "missing_key_prop":
        # .map() that returns JSX but none of the returned elements have key=
        for m_map in re.finditer(r'\.map\s*\(', content):
            start = m_map.end()
            # Grab up to 500 chars of context
            chunk = content[start:start + 500]
            if re.search(r'<[A-Z][a-zA-Z]*\b|<[a-z][a-z-]+\b', chunk) and not re.search(r'\bkey=', chunk):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "framer_no_reduced_motion":
        if re.search(r"from ['\"]framer-motion['\"]", content) and re.search(r'\bmotion\.', content):
            if not re.search(r'useReducedMotion', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "lazy_without_suspense":
        if re.search(r'(?:React\.)?lazy\s*\(', content) and not re.search(r'Suspense', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
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
        for m_av in re.finditer(r'<(?:video|audio)\b([^>]*)', content, re.IGNORECASE):
            attrs = m_av.group(1)
            if re.search(r'\bautoPlay\b|\bautoplay\b', attrs, re.IGNORECASE) and not re.search(r'\bmuted\b', attrs, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "select_no_label":
        for m_sel in re.finditer(r'<select\b([^>]*)', content, re.IGNORECASE):
            attrs = m_sel.group(1)
            # Check nearby (within 200 chars) for a label
            pos = m_sel.start()
            context = content[max(0, pos - 200):pos + 200]
            if not re.search(r'<label\b|aria-label=|aria-labelledby=', context, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "icon_aria_missing":
        for m_icon in re.finditer(r'<svg\b[^>]*>|<i\s+class=[^>]+>', content, re.IGNORECASE):
            pos = m_icon.start()
            context = content[max(0, pos - 100):pos + 200]
            if not re.search(r'aria-(?:label|hidden|labelledby)=', context, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "icon_only_button":
        for m_btn in re.finditer(r'<button\b([^>]*)>\s*<(?:svg|i)\b', content, re.IGNORECASE):
            attrs = m_btn.group(1)
            if not re.search(r'aria-label=', attrs, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
                break
        return issues

    if custom == "modal_no_aria":
        if re.search(r'(?:modal|Modal)', content) and not re.search(r'role=["\']dialog["\']', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "missing_aria_role":
        for m_el in re.finditer(r'<(?:div|span)\s[^>]*on(?:Click|Keydown|Keyup)[^>]*>', content, re.IGNORECASE):
            if not re.search(r'\brole=', m_el.group(0), re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
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
        if re.search(r"from ['\"]next/", content) and re.search(r'<img\b', content, re.IGNORECASE):
            if not re.search(r"from ['\"]next/image['\"]", content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "missing_loading_state":
        if re.search(r'\buseQuery\b', content) and not re.search(r'\bisLoading\b', content):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "missing_error_state":
        if re.search(r'\buseQuery\b', content) and re.search(r'\bisLoading\b', content):
            if not re.search(r'\bisError\b|\berror\b', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
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
        if re.search(r'grid-cols-3\b', content, re.IGNORECASE):
            # Flag if there are 3+ child elements with identical classNames (crude check)
            child_classes = re.findall(r'className=["\']([^"\']+)["\']', content)
            if len(child_classes) >= 3:
                from collections import Counter
                cls_counts = Counter(child_classes)
                if cls_counts.most_common(1)[0][1] >= 3:
                    issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                    "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "font_weight_extremes":
        if re.search(r'\bfont-bold\b', content) and re.search(r'\bfont-normal\b', content):
            if not re.search(r'\bfont-medium\b|\bfont-semibold\b', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "accordion_faq":
        if re.search(r'\bAccordion\b', content, re.IGNORECASE) and re.search(r'\bFAQ\b', content, re.IGNORECASE):
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "dark_mode_toggle":
        if re.search(r'(?:ThemeToggle|toggleDarkMode|DarkModeToggle|darkMode)', content, re.IGNORECASE):
            if not re.search(r'prefers-color-scheme', content, re.IGNORECASE):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "hardcoded_copyright_year":
        if re.search(r'©\s*20\d{2}|&copy;\s*20\d{2}', content, re.IGNORECASE):
            if not re.search(r'getFullYear\s*\(\s*\)', content):
                issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                                "issue": rule["description"], "command": rule["command"]})
        return issues

    if custom == "pricing_table":
        PRICING_KW = ['Free', 'Pro', 'Enterprise', 'Starter', 'Basic', 'Premium']
        count = sum(1 for kw in PRICING_KW if re.search(r'\b' + kw + r'\b', content, re.IGNORECASE))
        if count >= 3:
            issues.append({"id": rule["id"], "file": str(filepath.resolve()), "tier": rule["tier"],
                            "issue": rule["description"], "command": rule["command"]})
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
    "missing_tabular_nums": _analyze_html_custom_rule,
    "placeholder_only_input": _analyze_html_custom_rule,
    "srcset_missing": _analyze_html_custom_rule,
    "anchor_target_blank": _analyze_html_custom_rule,
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


def _analyze_rule(
    rule: dict,
    filepath: Path,
    content: str,
    ext: str,
    design_variance: int,
    dynamic_colors: dict[str, str] | None,
) -> list[dict]:
    """Analyze one configured rule against loaded source content."""
    issues = []
    # Skip rules conditioned on DESIGN_VARIANCE if below threshold
    variance_threshold = rule.get("_requires_variance_gt")
    if isinstance(variance_threshold, (int, float)) and design_variance <= variance_threshold:
        return issues

    custom = rule.get("_custom_check")
    handler = _CUSTOM_CHECK_HANDLERS.get(custom)
    if handler is not None:
        custom_issues = handler(rule, filepath, content, ext, dynamic_colors)
        if custom_issues is not None:
            return custom_issues

    # Standard regex match — flag once per file
    pattern = rule.get("pattern")
    if isinstance(pattern, re.Pattern):
        m = pattern.search(content)
        if m:
            line_number = content.count('\n', 0, m.start()) + 1
            col = m.start() - content.rfind('\n', 0, m.start())
            lines_list = content.splitlines()
            snippet = lines_list[line_number - 1].strip() if line_number <= len(lines_list) else ""
            issues.append({
                "id": rule["id"],
                "file": str(filepath.resolve()),
                "tier": rule["tier"],
                "issue": rule["description"],
                "command": rule["command"],
                "line": line_number,
                "column": col,
                "snippet": snippet,
            })
    return issues


def analyze_file(filepath: Path, design_variance: int = 8, dynamic_colors: dict[str, str] | None = None) -> list[dict]:
    """Scan a single file against all slop rules.

    Args:
        filepath: File to scan.
        design_variance: Current DESIGN_VARIANCE dial value (affects conditional rules).
        dynamic_colors: Tailwind configuration colors mappings.
    """
    issues = []
    ext = filepath.suffix.lower()

    # Filter rules that apply to this file extension
    applicable_rules = []
    for r in RULES:
        exts = r.get("exts", [])
        if isinstance(exts, (list, set, tuple)) and ext in exts:
            applicable_rules.append(r)
    if not applicable_rules:
        return issues

    try:
        # 1MB size guard to prevent regex engine freezing on massive bundled files
        if filepath.stat().st_size > 1_000_000:
            return issues

        content = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return issues  # Skip binary or unreadable files

    if HAS_AST:
        ast_issues = _analyze_ast(filepath, content, ext)
        issues.extend(ast_issues)

    # Component-level layout heuristics (runs regardless of AST)
    layout_issues = _analyze_component_layout(filepath, content, ext)
    issues.extend(layout_issues)

    for rule in applicable_rules:
        issues.extend(
            _analyze_rule(rule, filepath, content, ext, design_variance, dynamic_colors)
        )

    return issues

def analyze_directory(root_path: str = ".", exclude_paths: list[str] | None = None,
                      zone_overrides: dict[str, str] | None = None,
                      design_variance: int = 8,
                      target_files: list[str | Path] | None = None) -> list[dict]:
    """Walk directory and return a flat list of all detected slop issues.

    Args:
        root_path: Directory to scan.
        exclude_paths: Additional directory names/paths to skip (from ``uidetox exclude``).
        zone_overrides: File-to-zone mapping; files in 'vendor' or 'generated' zones are skipped.
        design_variance: DESIGN_VARIANCE dial value passed to per-file analysis.
        target_files: Optional files to analyze. ``None`` walks the full tree; an
            explicit empty list analyzes no files.
    """
    all_issues = []
    root = Path(root_path).resolve()
    file_set = ProjectFileSet(
        find_project_root(root),
        excludes=exclude_paths or (),
        zone_overrides=zone_overrides or {},
        explicit_targets=target_files,
        scope_root=root,
    )
    target_candidates = file_set.explicit_candidates(require_extension=False)
    target_candidate_set = set(target_candidates or ())
    analysis_targets = file_set.discover()

    from concurrent.futures import ThreadPoolExecutor
    from uidetox.color_utils import load_dynamic_colors, audit_project_colors, find_color_config_sources

    color_sources = find_color_config_sources(root)
    dynamic_colors = load_dynamic_colors(root)
    should_audit_colors = bool(color_sources) and (
        target_candidates is None
        or any(source.resolve() in target_candidate_set for source in color_sources)
    )
    color_audit_violations = audit_project_colors(root) if should_audit_colors else []
    color_issue_file = str((color_sources[0] if color_sources else root).resolve())

    def _analyze_wrapper(fp: Path) -> list:
        return analyze_file(fp, design_variance=design_variance, dynamic_colors=dynamic_colors) # type: ignore

    futures = []
    with ThreadPoolExecutor() as executor:
        for file_path in analysis_targets:
            futures.append(executor.submit(_analyze_wrapper, file_path)) # type: ignore

        for future in futures:
            all_issues.extend(future.result())

    # Project-level dynamic color audit based on actual Tailwind/theme tokens.
    # Cap output to keep the queue actionable rather than overwhelming.
    for violation in color_audit_violations[:8]:
        all_issues.append({
            "id": "LOW_CONTRAST_SLOP",
            "file": color_issue_file,
            "tier": "T1" if violation.get("severity") == "critical" else "T2",
            "issue": (
                f"Dynamic color audit: {violation['foreground']} on {violation['background']} "
                f"fails WCAG AA ({violation['ratio']}:1 < {violation['required']}:1)."
            ),
            "command": "Adjust the theme token pair to meet WCAG AA contrast, then rescan to verify the updated palette."
        })

    return all_issues
