import tree_sitter

HAS_AST = False
try:
    import tree_sitter_javascript as ts_js
    import tree_sitter_typescript as ts_ts
    import tree_sitter_css as ts_css
    HAS_AST = True
    JS_LANG = tree_sitter.Language(ts_js.language())
    TSX_LANG = tree_sitter.Language(ts_ts.language_tsx())
    CSS_LANG = tree_sitter.Language(ts_css.language())
except ImportError:
    pass

def _get_parser(ext: str):
    if not HAS_AST:
        return None
    parser = None
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        parser = tree_sitter.Parser(JS_LANG)
    elif ext in {".ts", ".tsx"}:
        parser = tree_sitter.Parser(TSX_LANG)
    elif ext in {".css", ".scss", ".less"}:
        parser = tree_sitter.Parser(CSS_LANG)
    return parser

def _analyze_ast(filepath, content: str, ext: str) -> list[dict]:
    parser = _get_parser(ext)
    if not parser:
        return []
        
    tree = parser.parse(content.encode("utf-8"))
    issues = []
    
    if ext in {".tsx", ".jsx", ".js", ".ts"}:
        # 1. Component Level Dashboard Slop Detection (HERO_DASHBOARD_SLOP via AST)
        # 2. Div Soup (DOM_SOUP_SLOP via AST)
        div_count = 0
        semantic_count = 0
        nested_ternaries = 0
        
        def walk(node):
            nonlocal div_count, semantic_count, nested_ternaries
            if node.type == "jsx_element" or node.type == "jsx_self_closing_element":
                open_tag = node.child_by_field_name("open_tag") if node.type == "jsx_element" else node
                if open_tag:
                    name_node = open_tag.child_by_field_name("name")
                    if name_node:
                        tag_name = name_node.text.decode("utf-8") if isinstance(name_node.text, bytes) else name_node.text
                        if tag_name == "div":
                            div_count += 1
                        elif tag_name in {"nav", "main", "article", "section", "aside", "header", "footer"}:
                            semantic_count += 1
            elif node.type == "ternary_expression":
                # Check if it has a nested ternary
                for child in node.children:
                    if child.type == "ternary_expression":
                        nested_ternaries += 1
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        
        if div_count > 20 and semantic_count == 0:
            issues.append({
                "file": str(filepath.resolve()),
                "tier": "T2",
                "issue": f"Div-heavy file with no semantic HTML elements detected via AST. ({div_count} divs, 0 semantic elements)",
                "command": "Replace generic divs with <nav>, <main>, <article>, <section>, <aside>, <header>, <footer>."
            })
            
        if nested_ternaries >= 2:
            issues.append({
                "file": str(filepath.resolve()),
                "tier": "T2",
                "issue": f"Nested ternary operator detected — harms readability in JSX. ({nested_ternaries} nested ternaries found)",
                "command": "Extract nested ternaries into named variables or early returns for clarity."
            })

    return issues
