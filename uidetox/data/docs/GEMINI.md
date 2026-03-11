## Gemini Integration

UIdetox works well with Google's Gemini models (via Gemini CLI, Google AI Studio, or GCP Vertex).

### 1. Installation

Run:
```bash
uidetox update-skill gemini
```

Because Gemini CLI uses a persistent configuration file, ensure your project's `GEMINI.md` (or equivalent context file) explicitly references the UIdetox SKILL:
```markdown
@./SKILL.md

# UI Directives
You are enforcing the Anti-Slop catalog defined in SKILL.md. Do not generate generic startup UI.
```

### 2. Autonomous Loop

Gemini models perform best with clear, structured multi-step contexts. Paste this prompt to trigger the loop:

> We are running UIdetox to clean this codebase.
> Initialize by running `uidetox setup` and `uidetox scan`.
> Read `.uidetox/state.json` or run `uidetox status` to view our starting Design Score.
> 
> YOUR PROTOCOL:
> 1. Run `uidetox autofix` to clear safe T1 mechanical issues. Resolve them via `uidetox resolve <ID> --note "reason"`.
> 2. Run `uidetox next` to get a file-batch of pending issues.
> 3. Edit the file to apply the design fixes (e.g., swapping layouts, injecting color).
> 4. Resolve the batch.
> 5. Print out the current `uidetox status`.
> Continue this protocol iteratively until our score reaches 95+.
