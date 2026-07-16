"""Tree-sitter parser setup and AST-based analyzer checks."""

import re
from pathlib import Path

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
