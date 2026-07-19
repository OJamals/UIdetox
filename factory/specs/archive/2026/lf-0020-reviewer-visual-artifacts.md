---
id: lf-0020
title: Generate reviewer-grade visual evidence artifacts
agent: codex
risk: medium
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_visual_evidence.py tests/test_capture.py tests/test_review.py tests/test_status.py
  - .venv/bin/python -m compileall -q uidetox
  - rtk git diff --check
---

# Grill Gate

- Owner: repository operator and subjective reviewers deciding whether a visual change is acceptable.
- Problem: the current amplified raw diff is hard to interpret, lacks localized crops and semantic prioritization, and offers no deterministic board for before/after review across viewports.
- Out of scope: replacing human/LLM subjective review, adding SSIM, scoring aesthetic quality, video capture, and redesigning the sample application's deliberately bad UI.
- Review failure: artifacts obscure unchanged context, color conversion silently corrupts images, contact sheets are nondeterministic, artifact generation is always expensive, or review/status omit incomplete viewports.
- Riskiest assumption: a small fixed artifact set—overlay, crop, blend, and contact sheet—provides enough context for reviewers without becoming an image editor.
- Smallest acceptable: changed viewports receive deterministic localized artifacts and the manifest/review output ranks changed semantic regions and exposes missing/incomplete evidence.
- Recommended choice accepted: fast exact comparison remains the default; reviewer artifact generation and archival compression are explicit controls.

# Context

Pillow is strongest as a decoding, masking, composition, color-management, and artifact-generation engine. It should prepare evidence for a reviewer, not decide whether the design is good.

# Acceptance Criteria

- Optional reviewer artifacts include a heat overlay on the after image, a padded changed-area crop, a 50% before/after blend, and a labeled multi-viewport contact sheet.
- Empty diffs do not generate misleading crops or overlays; the manifest records why an artifact was omitted.
- Artifact dimensions, labels, padding, colors, alpha, ordering, filenames, and hashes are deterministic.
- Imported/cross-machine images can opt into ICC-to-sRGB conversion using cached transforms; missing/invalid profiles produce explicit fallback warnings rather than silent failure.
- Native local screenshots retain the fast color path unless conversion is requested.
- Review and status text/JSON report top changed semantic regions, available reviewer artifacts, incomplete viewports, and warnings.
- Archival output supports explicit lossless PNG optimization/compression controls without changing comparison pixels or defaulting to a slow path.
- Public tests inspect artifact properties and manifest records rather than Pillow implementation internals.
- The full-stack fixture smoke produces readable evidence for at least desktop and one narrow viewport.

# Constraints

- Do not label changed-pixel percentage as quality, regression severity, or design score.
- Do not make ICC conversion mandatory for browser-native screenshots.
- Do not introduce a template/UI framework for contact sheets.
- Keep binary artifacts out of Git.

# Review Notes

- Visually inspect one generated contact sheet and crop from the full-stack fixture.
- Verify artifact hashes are stable across repeated identical runs.
- Verify semantic region ranking is deterministic under ties.
- Verify archival settings affect file encoding only, not manifest metrics.
