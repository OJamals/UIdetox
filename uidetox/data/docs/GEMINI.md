## Gemini Integration

UIdetox works well with Google's Gemini models (via Gemini CLI, Google AI Studio, or GCP Vertex).

### 1. Installation

Run:
```bash
uidetox update-skill gemini
```

This merges the bundle into `.gemini/skills/uidetox/`. It does not rewrite project-root `SKILL.md`, `AGENTS.md`, `GEMINI.md`, `commands/`, or `reference/` content.

### 2. Autonomous Loop

Run `uidetox loop` to dispatch Gemini into the full 5-phase protocol:

```bash
uidetox loop
```

The loop bootstraps with auto-detected tooling, continuation context from memory, and component-level batch commits. Gemini will:
1. Run `uidetox check --fix` to clear mechanical issues
2. Run `uidetox scan --path .` then systematically read every frontend file
3. Fix issues by component using `uidetox next` → fix all → `uidetox batch-resolve ID1 ID2 ... --note "..."`
4. Run `uidetox review` + `uidetox review --score N` for subjective quality assessment
5. Check `uidetox status` for blended Design Score (60% static + 40% LLM review)
6. Run `uidetox finish` to squash-merge the session branch

Progress auto-saves to memory. Re-running `uidetox loop` resumes from the last checkpoint.

### 3. Visual Regression + Port Configuration

Use `uidetox capture` to validate UI changes visually. **Start your dev server first** — UIdetox does not launch it.

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

Use `diff` to compare against the stored issue baseline and `watch` to keep analysis running while Gemini iterates.
