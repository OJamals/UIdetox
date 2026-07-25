# Plan 013: Secure repository evidence before persistence or agent injection

> **Executor instructions**: Follow this plan exactly. Never place a credential
> value in source, fixtures, logs, snapshots, commit messages, or plan updates.
> Run every verification gate. Update this plan's row in `plans/README.md` when
> done.
>
> **Drift check (run first)**:
> `git diff --stat d5898c9..HEAD -- uidetox/prompt_safety.py uidetox/analyzer_engine.py uidetox/analyzer_rules.py uidetox/commands/scan.py uidetox/commands/next.py uidetox/commands/batch_resolve.py uidetox/commands/loop.py uidetox/subagent.py tests/test_prompt_safety.py tests/test_regressions.py`
> If evidence construction or prompt rendering changed, stop and reconcile the
> plan against live code before editing.

## Status

- **Priority**: P0
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `d5898c9`, 2026-07-25

## Why this matters

UIdetox scans untrusted repositories and then persists and injects findings into
agent prompts. The hardcoded-credential rule currently copies the complete
matched line into issue evidence. Separately, compiler/linter/formatter output
is stored as memory and later printed under an instruction-bearing heading.
Both paths cross the repository-data/trusted-instruction boundary.

## Current state

- `uidetox/analyzer_engine.py:39-63` uses `pattern.search(content)` and stores
  `lines_list[line_number - 1].strip()` as `snippet`.
- `uidetox/analyzer_rules.py:1485-1493` defines
  `HARDCODED_SECRET_SLOP`; do not reproduce any matched value.
- `uidetox/commands/scan.py:492-523` emits analyzer dictionaries as JSON or
  copies their snippets into persistent queue state.
- `uidetox/commands/next.py:790-809` renders the persisted snippet into the
  agent work packet.
- `uidetox/commands/batch_resolve.py:157-185` stores truncated tool diagnostics
  as a memory note.
- `uidetox/commands/loop.py:143-154` prints notes beneath
  `MEMORY BANK (obey these during the loop)` without an untrusted-data wrapper.
- `uidetox/subagent.py:303-345` is the exemplar: repository-derived content is
  rendered with `render_untrusted_data`; trusted instructions remain outside.
- `uidetox/prompt_safety.py` already owns `render_untrusted_data`; extend this
  trust-boundary module instead of creating a parallel sanitizer module.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Focused tests | `python -m pytest -q -W error tests/test_prompt_safety.py tests/test_next_command.py tests/test_regressions.py -k 'secret or prompt or untrusted or snippet or memory'` | all selected tests pass |
| Full suite | `python -m pytest -q -W error` | exit 0; zero failures |
| Leak check | `python -m pytest -q -W error tests/test_prompt_safety.py -k 'sensitive_evidence_never_emitted'` | generated sentinel absent from every captured output/state surface |

## Scope

**In scope**:
- `uidetox/prompt_safety.py`
- `uidetox/analyzer_engine.py`
- `uidetox/commands/scan.py`
- `uidetox/commands/next.py`
- `uidetox/commands/batch_resolve.py`
- `uidetox/commands/loop.py`
- `uidetox/subagent.py`
- `tests/test_prompt_safety.py`
- `tests/test_next_command.py`
- `tests/test_regressions.py`

**Out of scope**:
- Changing the credential detector's matching coverage.
- Persisting encrypted credentials.
- Rotating real credentials; if a real credential is discovered, stop and
  report only its type and location.
- Redesigning the general finding schema; plan 015 owns that migration.

## Cleanup and replacement constraints

- Extend `prompt_safety.py`; do not create a second evidence-safety module.
- Replace raw interpolation at every migrated caller, then delete caller-local
  escaping/redaction helpers.
- Keep one recursive sanitizer and one untrusted-data renderer.
- Report production line delta and deleted helper count; added safety code
  should replace duplicated boundary handling where feasible.

## Git workflow

- Branch: `codex/013-secure-evidence-boundaries`
- Commit: `fix: quarantine untrusted finding evidence`
- Do not push or open a PR unless instructed.

## Steps

### Step 1: Characterize every leak surface

Add tests that construct a fake credential-shaped sentinel at runtime from
separate non-secret fragments. Run scan JSON output, queue persistence,
`uidetox next`, loop memory rendering, and self-healing diagnostics. Assert the
complete sentinel never appears in output or persisted state. Assert file,
line, rule ID, credential class, and a non-reversible fingerprint remain.

**Verify**: focused tests fail for the current implementation for the expected
leak assertions only.

### Step 2: Centralize evidence sanitization

Extend `uidetox/prompt_safety.py` with pure functions that:

- classify sensitive rule IDs and diagnostic fields;
- replace sensitive snippets with a fixed redaction marker;
- generate a SHA-256 fingerprint from the matched bytes without retaining them;
- recursively sanitize data before persistence or serialization;
- preserve source location and detector metadata.

Apply sanitization at evidence construction in `analyzer_engine.py`, then
defensively at scan serialization/persistence. Never rely only on output-time
redaction.

**Verify**: secret-focused tests pass; non-sensitive snippet tests remain exact.

### Step 3: Make every agent boundary explicit

Use `render_untrusted_data` for repository snippets, tool diagnostics, memory
patterns, and notes. Rename instruction-adjacent headings so they identify data
as context, not commands. Keep trusted recovery steps in a separate literal
block after the data wrapper.

**Verify**: hostile diagnostic and hostile memory tests show the payload inside
the untrusted-data envelope and never in trusted instruction text.

### Step 4: Prevent unsafe historical data from resurfacing

Sanitize queue issues and memory notes when loaded as well as when written.
This protects users with pre-fix `.uidetox/state.json` or memory files. Do not
rewrite files merely by reading them; write sanitized data only during the
normal next mutation.

**Verify**: tests loading legacy unsafe state render only redacted evidence.

### Step 5: Run regression and leak gates

Run focused tests, the full suite, and the leak check. Review captured pytest
output to ensure a failing test cannot print the sentinel through assertion
diffs; tests should compare hashes/containment without echoing raw values.

**Verify**: all commands in the table succeed.

## Test plan

- Credential finding retains type/location/fingerprint but not matched bytes.
- JSON, table, queue, history/memory, `next`, and loop outputs remain clean.
- Compiler/linter output containing instruction-like text stays untrusted.
- Legacy state is sanitized on consumption.
- Ordinary non-sensitive snippets retain current behavior.
- Model tests after `tests/test_prompt_safety.py`.

## Done criteria

- [ ] No sensitive matched line is persisted or emitted.
- [ ] All repository/tool-derived prompt content uses the untrusted-data boundary.
- [ ] Legacy unsafe state cannot re-enter a prompt unsanitized.
- [ ] Focused and full tests pass.
- [ ] Only in-scope files plus `plans/README.md` changed.
- [ ] Plan status updated.

## STOP conditions

- A real credential is found; report type/location only and request rotation.
- Safe redaction requires weakening credential detection.
- A public output contract requires raw secret snippets.
- Prompt rendering has moved to a different trust-boundary abstraction.

## Maintenance notes

Every future finding source must sanitize before persistence. Every future agent
prompt must separate trusted instructions from repository/tool data. Reviewers
should search new prompt surfaces for raw interpolation.
