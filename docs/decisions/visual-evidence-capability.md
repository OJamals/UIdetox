# ADR: Pillow visual-evidence boundary

Status: Accepted  
Date: 2026-07-19

## Decision

UIdetox uses Pillow for deterministic, local raster evidence:

- safely decode single-frame PNG inputs under explicit pixel and file limits;
- normalize alpha and optional embedded ICC profiles;
- compute exact or explicitly masked changed-pixel metrics;
- produce lossless diffs, heat overlays, changed-area crops, blends, and contact
  sheets for a human reviewer;
- persist source, normalized-image, context, request, and artifact hashes.

Pillow evidence supports review; it does not decide whether a design is good.
Semantic regions and intent provenance come from UIdetox's mapping layer, while
subjective design quality remains an agent/human review.

UIdetox does not use SSIM, LPIPS, OCR similarity, or another perceptual score.
Such a dependency will be considered only after a representative benchmark
corpus, documented failure modes, calibrated thresholds, and a clear decision
use are available. Exact changed-pixel coverage is intentionally legible and
reproducible.

## Input and execution contract

- Inputs are local files only. URL, data-URI, and network fetching are not
  supported.
- Animated or multi-frame PNG, GIF, and TIFF inputs are rejected instead of
  silently comparing only one frame.
- PNG output is lossless. Compression and optimization alter encoding cost and
  file size, not evidence semantics.
- Pillow remains optional. Install `uidetox[visual]` for local image comparison
  or `uidetox[capture]` for image comparison plus Playwright capture.
- Core scan, map, redesign, intent, and queue commands import without Pillow.

## Isolation and trust boundary

`uidetox visual-evidence --isolated` and `uidetox capture --isolated` move image
decoding into a dedicated Python process. Parent and worker exchange bounded,
versioned JSON; neither side accepts shell command strings, pickle, executable
payloads, or worker-selected paths.

The parent supplies allowed filesystem roots and request, output, stderr, file,
pixel, frame, wall-time, CPU-time, and memory limits. It treats the response as
untrusted, revalidates its schema and numeric ranges, checks request/source
hashes, confines artifacts to the requested output directory, and hashes the
produced files before accepting the manifest.

This is process isolation, not a complete OS sandbox. Linux applies an address
space limit in addition to CPU, file-size, descriptor, and wall-time bounds.
macOS does not provide a usable hard address-space rlimit to this worker, so the
remaining limits still apply but the memory setting is advisory there. A
service that accepts uploads from untrusted users must also place the worker in
a deployment-level sandbox or container with network denial, filesystem
mount isolation, and kernel-enforced memory limits.

## Consequences

The default in-process path remains fast and appropriate for trusted local
screenshots. External or less-trusted baselines can opt into the worker without
changing evidence semantics. Both modes emit the same typed manifest and are
covered by regression and fixture smoke tests.
