"""Visualization command: generates HTML treemaps and terminal trees of codebase health."""

import argparse
import json
from pathlib import Path
from collections import defaultdict
from uidetox.state import load_state, ensure_uidetox_dir, get_uidetox_dir


def run(args: argparse.Namespace):
    # Depending on how the command was invoked (viz or tree)
    cmd = getattr(args, "viz_cmd", "viz")
    path_root = Path(getattr(args, "path", "."))
    
    state = load_state()
    issues = state.get("issues", [])
    
    # Map issues to files
    issue_map = defaultdict(list)
    for issue in issues:
        # File paths in state are usually relative to project root
        issue_map[issue.get("file", "")].append(issue)
        
    if cmd == "tree":
        _render_tree(path_root, issue_map, max_depth=getattr(args, "depth", 3))
    else:
        _render_html_treemap(path_root, issue_map)


def _build_tree(root_path: Path, issue_map: dict) -> dict:
    """Builds a nested dictionary representing the directory structure with issue counts."""
    tree = {"name": root_path.name or str(root_path), "path": str(root_path), "type": "dir", "issues": 0, "children": {}}
    
    for file_path_str, file_issues in issue_map.items():
        if not file_path_str:
            continue
            
        parts = Path(file_path_str).parts
        current = tree
        current["issues"] += len(file_issues)
        
        for i, part in enumerate(parts):
            is_file = (i == len(parts) - 1)
            
            if part not in current["children"]:
                current["children"][part] = {
                    "name": part,
                    "path": "/".join(parts[:i+1]),
                    "type": "file" if is_file else "dir",
                    "issues": 0,
                    "issues_list": [] if is_file else None,
                    "children": {} if not is_file else None
                }
            
            current["children"][part]["issues"] += len(file_issues)
            if is_file:
                current["children"][part]["issues_list"].extend(file_issues)
                
            current = current["children"][part]

    return tree


def _print_tree(node: dict, indent: int, max_depth: int):
    # Format the current node
    prefix = "  " * indent
    name = f"{node['name']}/" if node["type"] == "dir" else node["name"]
    issue_count = node["issues"]
    
    if issue_count > 0:
        # Colorize issue count based on severity (if possible, sticking to basic for now)
        color_start = "\033[91m" if issue_count >= 5 else "\033[93m"
        color_end = "\033[0m"
        annotation = f" {color_start}⚠ {issue_count} issue(s){color_end}"
    else:
        annotation = ""
        
    if node["type"] == "file" or indent == 0 or issue_count > 0:
        print(f"{prefix}{name}{annotation}")
        
        # If it's a file with issues, optionally list the tiers
        if node["type"] == "file" and issue_count > 0:
            tiers = defaultdict(int)
            for issue in node["issues_list"]:
                tiers[issue.get("tier", "T4")] += 1
            tier_str = ", ".join(f"{count}×{t}" for t, count in sorted(tiers.items()))
            print(f"{prefix}  └─ {tier_str}")

    if node["type"] == "dir" and indent < max_depth and node["children"]:
        # Sort children: dirs first, then files, both sorted by issue count (descending)
        children = list(node["children"].values())
        children.sort(key=lambda x: (0 if x["type"] == "dir" else 1, -x["issues"], x["name"]))
        
        for child in children:
            if child["issues"] > 0 or child["type"] == "dir": # Only show paths leading to issues
                _print_tree(child, indent + 1, max_depth)


def _render_tree(root_path: Path, issue_map: dict, max_depth: int):
    print(f"\nUIdetox Health Tree (Max Depth: {max_depth})\n")
    if not issue_map:
        print("  Codebase is clean! No issues found. 🌱")
        return
        
    tree = _build_tree(root_path, issue_map)
    _print_tree(tree, 0, max_depth)
    print()


def _render_html_treemap(root_path: Path, issue_map: dict):
    ensure_uidetox_dir()
    output_path = get_uidetox_dir() / "treemap.html"
    
    if not issue_map:
        print("\n  Codebase is clean! No issues found to visualize. 🌱")
        return

    # Prepare data for a simple D3/ECharts style treemap or a nested HTML visualization
    # For a CLI robust solution without external dependencies, we generate a self-contained HTML file
    # utilizing basic CSS grid/flexbox based on the tree structure.
    
    tree = _build_tree(root_path, issue_map)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>UIdetox Heatmap</title>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 2rem; }}
        h1 {{ margin-top: 0; font-weight: 500; font-size: 1.5rem; color: #cbd5e1; }}
        .heatmap-container {{ display: flex; flex-wrap: wrap; gap: 4px; border-radius: 8px; overflow: hidden; }}
        .file-block {{ 
            flex-grow: 1; 
            min-height: 100px;
            display: flex; 
            align-items: center; 
            justify-content: center; 
            padding: 1rem; 
            box-sizing: border-box;
            transition: transform 0.2s, z-index 0.2s;
            position: relative;
        }}
        .file-block:hover {{ transform: scale(1.02); z-index: 10; cursor: pointer; }}
        .file-info {{ text-align: center; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }}
        .file-name {{ font-weight: 600; font-size: 0.9rem; word-break: break-all; }}
        .issue-count {{ font-size: 1.5rem; font-weight: 800; margin-top: 4px; }}
        
        /* Heatmap Colors based on issue density */
        .heat-1 {{ background: #334155; }} /* 1 issue */
        .heat-2 {{ background: #b45309; }} /* 2-3 issues */
        .heat-3 {{ background: #be123c; }} /* 4-7 issues */
        .heat-4 {{ background: #881337; }} /* 8+ issues */

        .tooltip {{
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0,0,0,0.9);
            padding: 8px;
            border-radius: 4px;
            font-size: 0.8rem;
            width: max-content;
            max-width: 300px;
            display: none;
            z-index: 20;
            margin-bottom: 8px;
            pointer-events: none;
        }}
        .file-block:hover .tooltip {{ display: block; }}
        .tooltip ul {{ margin: 4px 0 0; padding-left: 20px; text-align: left; }}
    </style>
</head>
<body>
    <h1>UIdetox Codebase Heatmap</h1>
    <p>Visualizing hot spots of AI Slop and design issues across {len(issue_map)} files.</p>
    
    <div class="heatmap-container">
"""
    
    # Flatten just the files with issues for the simple heatmap
    files_with_issues = []
    for file_path, file_issues in issue_map.items():
        if not file_path: continue
        files_with_issues.append({
            "path": file_path,
            "name": Path(file_path).name,
            "issues": len(file_issues),
            "issue_details": file_issues
        })
        
    # Sort by issue count descending
    files_with_issues.sort(key=lambda x: -x["issues"])
    
    for f in files_with_issues:
        heat_class = "heat-1"
        if f["issues"] >= 8: heat_class = "heat-4"
        elif f["issues"] >= 4: heat_class = "heat-3"
        elif f["issues"] >= 2: heat_class = "heat-2"
        
        # Calculate flexible width based on issue weight (more issues = larger block)
        flex_basis = f["issues"] * 50
        
        tooltip_li = "".join(f"<li>[{i.get('tier', '?')}] {i.get('issue', '')}</li>" for i in f["issue_details"])
        
        html_content += f"""
        <div class="file-block {heat_class}" style="flex-basis: {flex_basis}px;">
            <div class="file-info">
                <div class="file-name">{f["name"]}</div>
                <div class="issue-count">{f["issues"]}</div>
            </div>
            <div class="tooltip">
                <strong>{f["path"]}</strong>
                <ul>{tooltip_li}</ul>
            </div>
        </div>
        """
        
    html_content += """
    </div>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print(f"\n✅ Visualization generated successfully.")
    print(f"  Heatmap written to: {output_path}")
    print(f"  Open in browser: file://{output_path.resolve()}\n")
