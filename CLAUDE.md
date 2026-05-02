<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **UIdetox** (3610 symbols, 4863 relationships, 164 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale or fails because `.gitnexus/lbug` is missing, refresh the local index first. Prefer:
> `pnpm --allow-build=@ladybugdb/core --allow-build=tree-sitter --allow-build=tree-sitter-c --allow-build=tree-sitter-c-sharp --allow-build=tree-sitter-cpp --allow-build=tree-sitter-dart --allow-build=tree-sitter-go --allow-build=tree-sitter-java --allow-build=tree-sitter-javascript --allow-build=tree-sitter-kotlin --allow-build=tree-sitter-php --allow-build=tree-sitter-python --allow-build=tree-sitter-ruby --allow-build=tree-sitter-rust --allow-build=tree-sitter-swift --allow-build=tree-sitter-typescript --allow-build=tree-sitter-cli dlx gitnexus analyze`
> Add `--embeddings` if `.gitnexus/meta.json` reports embeddings > 0. If `pnpm` is unavailable, fall back to `npx gitnexus analyze`.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/UIdetox/context` | Codebase overview, check index freshness |
| `gitnexus://repo/UIdetox/clusters` | All functional areas |
| `gitnexus://repo/UIdetox/processes` | All execution flows |
| `gitnexus://repo/UIdetox/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

### Local refresh commands

- Re-index: `pnpm --allow-build=@ladybugdb/core --allow-build=tree-sitter --allow-build=tree-sitter-c --allow-build=tree-sitter-c-sharp --allow-build=tree-sitter-cpp --allow-build=tree-sitter-dart --allow-build=tree-sitter-go --allow-build=tree-sitter-java --allow-build=tree-sitter-javascript --allow-build=tree-sitter-kotlin --allow-build=tree-sitter-php --allow-build=tree-sitter-python --allow-build=tree-sitter-ruby --allow-build=tree-sitter-rust --allow-build=tree-sitter-swift --allow-build=tree-sitter-typescript --allow-build=tree-sitter-cli dlx gitnexus analyze`
- Re-index with embeddings: `pnpm --allow-build=@ladybugdb/core --allow-build=tree-sitter --allow-build=tree-sitter-c --allow-build=tree-sitter-c-sharp --allow-build=tree-sitter-cpp --allow-build=tree-sitter-dart --allow-build=tree-sitter-go --allow-build=tree-sitter-java --allow-build=tree-sitter-javascript --allow-build=tree-sitter-kotlin --allow-build=tree-sitter-php --allow-build=tree-sitter-python --allow-build=tree-sitter-ruby --allow-build=tree-sitter-rust --allow-build=tree-sitter-swift --allow-build=tree-sitter-typescript --allow-build=tree-sitter-cli dlx gitnexus analyze --embeddings`
- Fallback when `pnpm` is unavailable: `npx gitnexus analyze`

<!-- gitnexus:end -->