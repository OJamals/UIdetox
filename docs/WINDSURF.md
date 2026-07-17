## Windsurf Integration

UIdetox integrates deeply into Windsurf's cascading rules and memory systems.

### 1. Installation

Run:
```bash
uidetox update-skill windsurf
```

This merges the bundle into `.windsurf/skills/uidetox/`. It preserves project-root files, `.windsurfrules`, and unrelated installed skills.

### 2. Autonomous Loop

Run `uidetox loop` to dispatch Windsurf's Cascade into the full 5-phase protocol:

```bash
uidetox loop
```

The loop guides the agent through:
1. Mechanical fixes (`uidetox check --fix`)
2. LLM-dynamic codebase exploration + design audit (`uidetox scan`)
3. Component-level batch fixes (`uidetox next` → fix → `uidetox batch-resolve ID1 ID2 ... --note "..."`)
4. Subjective review with blended Design Score (`uidetox review` → `uidetox status`)
5. Finalize (`uidetox finish`)

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.

### 3. Visual Regression + Port Configuration

Use `uidetox capture` when validating a redesigned flow. **Start your dev server first** — UIdetox does not launch it.

Install capture support and Chromium once before first use:

```bash
pip install 'uidetox[capture]'
python -m playwright install chromium
```

```bash
pnpm dev
uidetox capture --stage before
uidetox capture --stage after

# Override a non-standard port
uidetox capture --stage before --url http://localhost:5173
```

To persist the target URL, set `dev_server` in `.uidetox/config.json`:

```json
{
  "dev_server": "http://localhost:5173"
}
```

Resolution order is: `--url` → `.uidetox/config.json` `dev_server` → `http://localhost:3000`.

### 4. Diff + Watch Utilities

```bash
uidetox diff
uidetox diff --since <sha>
uidetox watch
uidetox watch --path src/
```

Use `diff` to compare against the stored issue baseline and `watch` to keep analysis running while Cascade iterates.
