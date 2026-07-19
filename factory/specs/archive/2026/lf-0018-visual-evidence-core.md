---
id: lf-0018
title: Build a safe deterministic Pillow visual-evidence core
agent: codex
risk: high
grill: completed
verification:
  - .venv/bin/python -m pytest -q tests/test_visual_evidence.py tests/test_capture.py tests/test_optional_dependencies.py
  - .venv/bin/python -m compileall -q uidetox
  - rtk git diff --check
---

# Grill Gate

- Owner: repository operator and UIdetox users capturing local application evidence.
- Problem: visual comparison is embedded in `commands/capture.py`, silently resizes dimension mismatches, iterates pixels in Python, has no stable typed manifest, and persists desktop/responsive evidence inconsistently.
- Out of scope: semantic DOM ownership, reviewer contact sheets, perceptual similarity scoring, browser-server startup, and unrelated analyzer or redesign changes.
- Review failure: malformed or oversized images can exhaust resources, animated inputs are accepted accidentally, size mismatches are hidden, exact metrics change, responsive evidence is not persisted, or Pillow becomes a required core dependency.
- Riskiest assumption: Pillow can remain an optional capture dependency while a strict module-level contract gives every consumer deterministic evidence.
- Smallest acceptable: one typed request produces one versioned manifest through safe PNG loading, native Pillow operations, exact metrics, and atomic artifact persistence for every viewport.
- Recommended choice accepted: keep Pillow optional, require Pillow 12.3.0 or newer in capture-related extras, reject rather than resize incompatible inputs, and preserve exact RGB comparison as the default.

# Context

`uidetox.commands.capture._generate_visual_diff` currently owns loading, normalization, resizing, diffing, metrics, amplification, and loosely typed error dictionaries. The tuple loop is materially slower than native Pillow operations. `after --responsive` does not write the metadata consumed by review.

# Acceptance Criteria

- A deep `uidetox.visual_evidence` module exposes a typed `VisualEvidenceRequest` to `VisualEvidenceManifest` boundary; Pillow image objects remain private.
- The manifest has an explicit schema version, request parameters, source hashes, image dimensions/modes, exact changed-pixel metrics, artifact records, warnings, and freshness inputs.
- PNG loading uses context-managed lifecycle, verifies decoding, enforces a configurable pixel limit, treats decompression-bomb warnings as errors, rejects corrupt and multi-frame inputs, normalizes alpha/mode deterministically, and never mutates source files.
- Dimension mismatches fail with actionable evidence; no resize-to-match behavior remains.
- Diff computation uses native Pillow primitives (`ImageChops`, point masks, histograms/bounding boxes/statistics) without Python tuple-per-pixel loops or deprecated `getdata()` fallback paths.
- Exact zero-difference, threshold-boundary, alpha, mode-normalization, and changed-pixel metrics are covered by public-interface tests.
- Before/after capture persists desktop and responsive/page evidence uniformly through atomic JSON/image writes and maintains a deterministic latest manifest.
- Legacy desktop `diff_meta.json` and `latest.png` consumers either remain compatible or are migrated in the same increment.
- Pillow remains absent from the core dependency set and is raised to `>=12.3.0` in each capture-capable extra.
- Tests cover corrupt, wrong-format, oversized, multi-frame, alpha, dimension mismatch, threshold, exact metrics, missing Pillow, and responsive persistence.

# Constraints

- Do not expose Pillow classes in public annotations or serialized state.
- Do not infer semantic quality from raw changed-pixel percentage.
- Preserve `uidetox capture` command compatibility unless stricter failure is required for correctness.
- Use integration-style tests through the visual-evidence public API and capture CLI boundary; mock only Playwright/browser boundaries.

# Review Notes

- Verify hostile image handling occurs before expensive transforms.
- Verify threshold semantics are documented and tested at the boundary value.
- Verify every opened image is closed and every manifest write is atomic.
- Verify no silent resize, tuple loop, or Pillow core import remains.
