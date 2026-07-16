# Plan 005: Emit standalone machine-readable scan output

> **Executor instructions**: Preserve human table output while making JSON and
> GitHub modes automation-safe. Run every verification. Update plan index when done.
>
> **Drift check (run first)**: `git diff --stat 55fc6f3..HEAD -- uidetox/commands/scan.py uidetox/cli.py tests/test_regressions.py`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: `plans/001-reproducible-verification.md`
- **Category**: bug
- **Planned at**: commit `55fc6f3`, 2026-07-15

## Why this matters

`scan --output json` is advertised for automation but writes banners, path, dials,
tooling summaries, and analyzer status to stdout before the JSON document. Direct
`json.loads(stdout)` therefore fails. GitHub annotation mode has the same output
channel risk. Machine modes need a strict stdout contract; diagnostics belong on
stderr.

## Current state

```python
# uidetox/commands/scan.py:81-85
print("+" + "=" * 58 + "+")
print("| SCAN CODEBASE -- Static Analysis + Subjective Review     |")
print(f"  Path  : {scan_path}")
print(f"  Dials : VARIANCE={variance}  MOTION={intensity}  DENSITY={density}")

# output mode is not read until line 134
output_format = getattr(args, "output", "table")
```

At `:179-182`, JSON is printed after the prefix. Existing scan tests use argparse
namespaces and monkeypatch analyzer/tooling; follow `tests/test_regressions.py:352-453`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted | `python -m pytest -q tests/test_regressions.py -k 'scan and (json or github or output)'` | all selected tests pass |
| Full | `python -m pytest -q` | all pass |

## Scope

**In scope**:
- `uidetox/commands/scan.py`
- `uidetox/cli.py` only if help text needs contract clarification
- `tests/test_regressions.py`

**Out of scope**:
- Changing JSON issue schema.
- Adding SARIF or new output formats.
- Changing queue persistence in table mode; plan 004 owns that.
- Rewriting static analyzer behavior.

## Git workflow

- Branch: `codex/005-machine-readable-scan-output`
- Commit: `fix: emit clean machine-readable scan output`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Select output mode before any output

Read and validate `args.output` at start of `scan.run`, before tooling detection or
banner printing. Define explicit helpers/predicates for `table`, `json`, and `github`
rather than scattering string comparisons.

**Verify**: code search shows first stdout `print` occurs only after output mode is known.

### Step 2: Enforce stdout contracts

- `table`: preserve existing human output.
- `json`: stdout contains exactly one JSON document representing issue list.
- `github`: stdout contains only GitHub annotation lines; zero banners.
- Diagnostics/fallback warnings in machine modes go to stderr.

Tooling detection may still update config, but must not leak human status to machine
stdout. Do not include subjective-review prose in machine modes.

**Verify**: tests call `json.loads(capsys.readouterr().out)` successfully and assert no text precedes/follows document.

### Step 3: Cover empty/error cases

Add tests for empty issue list (`[]`), one issue including optional line/column/snippet,
invalid/missing git SHA fallback diagnostics, and GitHub T1/T2 warning vs T3/T4 error.

**Verify**: targeted tests pass.

## Test plan

- JSON output parses directly and retains current fields.
- Human banner absent in JSON/GitHub modes and present in table mode.
- Stderr may contain diagnostics without corrupting stdout.
- GitHub output contains one annotation per finding.
- Model new tests after existing scan namespace/monkeypatch tests at
  `tests/test_regressions.py:352-453`.

## Done criteria

- [ ] `json.loads(stdout)` succeeds for empty and populated scans.
- [ ] GitHub mode emits annotations only.
- [ ] Table output remains human-readable and existing tests pass.
- [ ] Full suite passes.
- [ ] Only in-scope files plus plan index changed.
- [ ] `plans/README.md` status row updated.
- [ ] Plan status updated.

## STOP conditions

- External documented consumers depend on banner-prefixed JSON.
- Clean JSON requires changing issue schema.
- Output routing requires editing commands other than scan.
- Existing output tests contradict documented `--output` behavior.

## Maintenance notes

Treat stdout as API for every non-table mode. New diagnostics must use stderr.
Review future output-format additions with parseability tests before release.
