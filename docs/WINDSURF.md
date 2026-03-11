## Windsurf Integration

UIdetox integrates deeply into Windsurf's cascading rules and memory systems.

### 1. Installation

Run:
```bash
uidetox update-skill windsurf
```
Because Windsurf uses Global Rules and Workspace Rules, we recommend placing the core UIdetox directives into `.windsurfrules`:

```markdown
# UI Directives (Anti-Slop)
Before writing any frontend code (React, Vue, HTML/CSS), you MUST refer to `SKILL.md` to avoid generic AI aesthetics.
Specifically: DO NOT use purple/blue default gradients, Inter fonts, or bouncy excessive animations. Adhere to the Design Variance, Motion Intensity, and Visual Density scores defined in `.uidetox/config.json`.
```

### 2. Autonomous Loop

Windsurf’s Cascade agents can easily chain terminal commands. Paste this prompt:

> We are running a UIdetox cleanup on this repository.
> 1. Run `uidetox scan` to assess the frontend tier.
> 2. Run `uidetox autofix` first to clear out T1 formatting/linting mechanical issues. Record resolutions using `uidetox resolve <ID> --note "..."`.
> 3. Run `uidetox next` to retrieve a batch of design issues for a specific file.
> 4. Modify the file using your Cascade editing tools to align the UI with our SKILL bounds.
> 5. Resolve the batch with notes, and run `uidetox status` to monitor progress.
> 6. Cascade this loop autonomously until we hit a Design Score greater than 95.
