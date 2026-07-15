<!-- codebase-memory-mcp:start -->
# Codebase Knowledge Graph (codebase-memory-mcp)

Use codebase-memory MCP graph tools before grep, glob, or file search for code discovery.

## Priority Order

1. `search_graph` — find functions, classes, routes, and variables
2. `trace_path` — trace callers, callees, data flow, and cross-service paths
3. `get_code_snippet` — read exact source for a resolved symbol
4. `query_graph` — run complex Cypher queries
5. `get_architecture` — inspect high-level structure, layers, hotspots, and clusters
6. `search_code` — search literals or patterns with graph context

If the project is not indexed, run `index_repository` before exploration. Before editing an existing symbol, use `trace_path` with `direction="inbound"` and `risk_labels=true`, then report HIGH or CRITICAL blast radius. Use `get_code_snippet` only after `search_graph` resolves the exact qualified name.

Fall back to grep or glob for string literals, error messages, config values, and non-code files when graph tools are insufficient.
<!-- codebase-memory-mcp:end -->
