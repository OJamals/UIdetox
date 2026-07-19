# Pillow integration research

Date: 2026-07-19
Scope: Pillow's useful role in UIdetox screenshot capture, visual comparison, evidence persistence, responsive review, performance, robustness, and security.

## Decision

Keep Pillow as an optional `capture` dependency. Deepen its use inside a dedicated visual-evidence subsystem. Do not move it into core analysis, AST parsing, semantic mapping, intent provenance, or redesign planning.

"Use all Pillow features" would be harmful. Pillow is a broad image-processing library; UIdetox needs a narrow, deterministic subset:

1. safe PNG decoding and normalization;
2. exact before/after pixel comparison;
3. threshold masks and image statistics;
4. semantic-region masks from runtime DOM bounds;
5. review-friendly diff visualizations;
6. controlled evidence serialization.

Highest-value change is architectural: consolidate screenshot acquisition around `runtime_observer.observe_frontend()`, then make a new Pillow-backed visual-evidence module consume its screenshots and `RuntimeElement.bounds`. This removes the duplicate Playwright path in `capture.py` and connects pixel evidence to UIdetox's existing semantic runtime map.

## Current implementation

| Seam | Current behavior | Assessment |
| --- | --- | --- |
| `uidetox/commands/capture.py:48-77` | `_capture_screenshot()` launches Chromium, captures one full-page PNG, then closes it. | Duplicates the richer runtime-observer capture path and launches a browser for every responsive screenshot. |
| `uidetox/commands/capture.py:80-99` | `_capture_multi_viewport()` captures mobile, tablet, desktop, and wide images. | Good viewport concept, but results are not persisted in one versioned evidence manifest. |
| `uidetox/commands/capture.py:102-167` | `_generate_visual_diff()` opens images, resizes dimension mismatches, converts to RGB, uses `ImageChops.difference()`, counts pixels in Python, amplifies deltas 8×, saves a PNG, and returns a dictionary. | Useful prototype. Not yet robust enough for authoritative regression evidence. |
| `uidetox/commands/capture.py:170-264` | Desktop comparison writes `diff_meta.json`; responsive comparisons only print results. | Evidence model is inconsistent. |
| `uidetox/commands/review.py:124-193` | Review trusts any existing `diff_meta.json` and separately detects responsive screenshots. | No hash/freshness validation; stale or partial evidence can influence review. |
| `uidetox/runtime_observer.py:43-69` | `RuntimeElement` already records selector, role, name, bounds, styles, and states. | Strong source for semantic region masks and component-local change evidence. |
| `uidetox/runtime_observer.py:120-215` | `observe_frontend()` reuses one browser across URLs/viewports, captures screenshots, and returns structured page/runtime evidence. | Better acquisition foundation than `capture.py`'s independent browser path. |
| `pyproject.toml:35-50` | Pillow is optional through `uidetox[capture]` and included in development/all extras. Minimum is `Pillow>=10.0.0`. | Optional placement is correct. Minimum should be reconsidered before adopting newer APIs. |

## Required design: one capture and evidence pipeline

```text
runtime_observer.observe_frontend()
    -> CaptureSet
       URL + viewport + screenshot + RuntimeElement bounds/styles/states
    -> visual_evidence.py (Pillow boundary)
       decode -> normalize -> geometry policy -> diff -> masks/stats -> artifacts
    -> visual-evidence.json
       hashes + provenance + per-page/per-viewport/per-region findings
    -> review / status / history / loop / finish
```

Recommended module boundaries:

- `runtime_observer.py`: browser acquisition and DOM/runtime facts only.
- `visual_evidence.py`: Pillow import boundary, typed image normalization, comparison, visualization, and manifest creation.
- `commands/capture.py`: CLI orchestration only.
- `review.py`: consumes validated evidence; performs no raw image processing.

This keeps Pillow optional: importing or running non-capture commands must not import `PIL`.

Proposed public module shape:

```python
@dataclass(frozen=True)
class VisualEvidencePolicy:
    pixel_threshold: int = 30
    max_file_bytes: int = 50_000_000
    max_pixels: int = 60_000_000
    alpha_background: str = "#ffffff"
    dimension_policy: Literal["strict", "pad_for_review"] = "strict"
    color_policy: Literal["record", "normalize_srgb"] = "record"

@dataclass(frozen=True)
class VisualEvidenceRequest:
    before: RuntimeObservation
    after: RuntimeObservation
    output_dir: Path
    policy: VisualEvidencePolicy
    preserve_regions: tuple[EvidenceRegion, ...] = ()
    ignore_regions: tuple[EvidenceRegion, ...] = ()

def build_visual_evidence(
    request: VisualEvidenceRequest,
) -> VisualEvidenceManifest: ...
```

This is the external interface and test surface: one request, one immutable manifest.
PNG loading, normalized Pillow images, per-page comparison, masks, statistics,
artifact rendering, and atomic persistence remain private implementation details.
CLI/review code exchanges UIdetox value objects and serialized manifests, never mutable
`PIL.Image.Image` objects or loose dictionaries.

## Priority recommendations

### P0: safe, deterministic decode lifecycle

Use `Image.open(path, formats=("PNG",))` inside a context manager, force `load()`, then copy the normalized pixels needed after the context exits. `Image.open()` is lazy; pixel data is not decoded until processing or `load()`. Pillow recommends a context manager or explicit `close()` for opened files. The `formats` argument restricts which format plugins are attempted. Sources: [Image.open()](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.open), [file lifecycle](https://pillow.readthedocs.io/en/stable/reference/open_files.html#image-lifecycle), [security guidance](https://pillow.readthedocs.io/en/stable/handbook/security.html#spoofing).

Treat images outside the just-completed Playwright capture as untrusted:

- allow only PNG;
- enforce a file-size limit before Pillow;
- preserve Pillow's `MAX_IMAGE_PIXELS`;
- promote `Image.DecompressionBombWarning` to an error;
- add a lower application-specific width, height, and total-pixel ceiling;
- reject truncated/corrupt images; never enable `ImageFile.LOAD_TRUNCATED_IMAGES`;
- reject multi-frame/APNG input for comparison.

Pillow warns at `MAX_IMAGE_PIXELS` and raises `DecompressionBombError` beyond twice the threshold. Its security guide recommends format allowlists, practical limits below the global maximum, current dependencies, metadata stripping, and structured logging. Sources: [decompression-bomb behavior](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.open), [Pillow security recommendations](https://pillow.readthedocs.io/en/stable/handbook/security.html#recommendations), [PNG text limits](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#opening).

Catch typed failures such as `PIL.UnidentifiedImageError`, `Image.DecompressionBombError`, and `OSError`. Persist a typed failed-evidence result. Do not hide arbitrary errors behind the current broad `except Exception` plus `"?"% (unknown)` success-like output.

#### `verify()` policy

Do not call `verify()` for every Playwright-generated screenshot. UIdetox must decode pixels anyway, and `load()` performs that work. `verify()` checks file integrity without decoding pixel data and requires reopening before later loading, so unconditional use adds another open/read cycle. Use it only at a distinct external-baseline import boundary when early validation before storage is useful. Source: [Image.verify()](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.verify).

### P0: normalize modes, alpha, orientation, and color explicitly

Current `convert("RGB")` silently discards alpha semantics. Normalize both inputs using one declared background:

1. convert to `RGBA`;
2. alpha-composite onto a configured opaque background, normally the captured page background;
3. convert the composite to `RGB`;
4. record original mode and normalization policy.

`Image.alpha_composite()` requires matching size and compatible alpha modes. Pillow distinguishes `RGB`, `RGBA`, and premultiplied-alpha modes. Sources: [alpha_composite()](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.alpha_composite), [Pillow modes](https://pillow.readthedocs.io/en/stable/handbook/concepts.html#modes).

`ImageOps.exif_transpose()` is useful only for externally imported baselines. Playwright PNGs should not need orientation repair. If arbitrary user-supplied image baselines become supported, transpose once during import and record that normalization. Source: [ImageOps.exif_transpose()](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose).

Color management should be conditional:

- record whether each image contains an ICC profile and store its hash, not raw bytes;
- if profiles match, compare normalized pixels without an extra transform;
- if profiles differ, optionally transform both to sRGB with `ImageCms.profileToProfile()`;
- check `features.check_module("littlecms2")` before requiring that path;
- if a profile is absent, record the configured sRGB assumption.

`Image.convert("RGB")` changes mode; it is not a substitute for ICC profile conversion. `ImageCms` applies profile-based transforms, and LittleCMS availability is detectable through `PIL.features`. Sources: [ImageCms](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html), [Pillow feature detection](https://pillow.readthedocs.io/en/stable/reference/features.html).

### P0: never resize screenshots to make comparison possible

Current code resizes mismatched images to their maximum width/height with LANCZOS. This geometrically distorts pixels and manufactures interpolation differences.

Use this policy:

- equal dimensions: compare directly;
- different dimensions: emit `dimension_mismatch` with original sizes;
- strict regression mode: fail comparison;
- review visualization mode: place both images, top-left aligned, onto equal-size canvases without resampling, using `Image.new()` plus `paste()`; mark padded territory separately;
- never use resized/padded visualization pixels as though they were exact same-coordinate regression metrics.

`ImageOps.fit()` crops; `ImageOps.pad()` preserves aspect ratio by resizing and padding. Both are suitable for equal-size contact-sheet thumbnails, not authoritative pixel alignment. Source: [ImageOps sizing behavior](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#resize-relative-to-a-given-size).

### P0: replace Python pixel iteration with Pillow-native masks

Keep `ImageChops.difference()`: it returns absolute per-pixel channel differences and is the correct exact-delta primitive. Source: [ImageChops.difference()](https://pillow.readthedocs.io/en/stable/reference/ImageChops.html#PIL.ImageChops.difference).

Replace `sum(1 for px in pixel_data if sum(px) > 30)` with C-backed image operations:

1. split RGB difference into single-band channels;
2. combine channel values under an explicit, versioned threshold rule;
3. build a binary `L` change mask;
4. obtain changed count from `mask.histogram()`;
5. obtain changed bounds from `mask.getbbox()`;
6. compute per-band magnitude using `ImageStat.Stat`.

Useful evidence fields:

- `changed_pixels`;
- `changed_ratio`;
- `changed_bbox`;
- `bbox_area_ratio`;
- per-channel `mean`, `rms`, and `extrema`;
- changed-pixel-only statistics using the binary mask;
- geometry mismatch status;
- threshold/tolerance policy version.

`ImageStat` calculates global or masked statistics and exposes count, extrema, mean, median, RMS, sum, and standard deviation. It uses 256-bin histograms, which is appropriate for normalized 8-bit `RGB`/`L` evidence. Sources: [ImageStat](https://pillow.readthedocs.io/en/stable/reference/ImageStat.html), [Image.getbbox() and histogram()](https://pillow.readthedocs.io/en/stable/reference/Image.html#the-image-class).

The simplest compatible implementation preserves the current `sum(R, G, B) > 30` rule:

```python
diff = ImageChops.difference(before_rgb, after_rgb)
r, g, b = diff.split()
magnitude = ImageChops.add(ImageChops.add(r, g), b)
mask = magnitude.point(lambda value: 255 if value > threshold else 0)
changed_pixels = mask.histogram()[255]
changed_bbox = mask.getbbox()
stats = ImageStat.Stat(diff)
```

`ImageChops.add()` clips at 255. Clipping cannot alter a `> 30` result, but this algorithm is not equivalent to an unbounded channel sum for configurable thresholds above 254. Constrain the threshold to `0..254` or version a different magnitude algorithm.

Local synthetic benchmark, Pillow 12.3.0, 1920×1080:

- current tuple/Python pixel loop: 0.2923 s average;
- `ImageChops.add()` + `point()` + histogram: 0.0069 s average;
- identical changed count: 842,001;
- observed speedup: about 42.4×.

This native path works without `ImageMath`. Do not add `ImageMath` merely for feature coverage. If future derived expressions need it, use `lambda_eval()`, never `unsafe_eval()`: `unsafe_eval()` invokes Python `eval()` and is explicitly unsafe for user-controlled strings. Sources: [ImageMath](https://pillow.readthedocs.io/en/stable/reference/ImageMath.html), [10.3.0 security/API change](https://pillow.readthedocs.io/en/stable/releasenotes/10.3.0.html#imagemath-eval).

UIdetox currently permits Pillow 10.0.0. Given UIdetox requires Python 3.11 and Pillow 12 supports Python 3.11-3.14, raise the floor to the current stable release and test both the minimum and latest compatible versions in CI. This is a security/maintenance decision, not a requirement of the `ImageChops` algorithm. Pillow's security guide says it supports the latest version and recommends keeping Pillow/C dependencies current. Sources: [Python support matrix](https://pillow.readthedocs.io/en/stable/installation/python-support.html), [security reporting/support statement](https://pillow.readthedocs.io/en/stable/handbook/security.html#reporting-a-vulnerability).

### P0: semantic region evidence

Raw page-wide change percentage cannot determine whether a redesign improved quality. Use existing runtime facts:

1. convert each `RuntimeElement.bounds` rectangle into an `L` mask with `ImageDraw`;
2. intersect that mask with the thresholded change mask;
3. compute `ImageStat.Stat(diff, mask=region_change_mask)`;
4. persist changed ratio/magnitude per selector, role, name, and semantic kind;
5. associate findings with frontend-map nodes and source ownership where available.

Runtime bounds are CSS pixels. Scale by captured device-pixel ratio, account for full-page scroll coordinates, round under a declared policy, and clip rectangles to image bounds before drawing.

Support explicit ignore regions separately. User/config-selected selectors may mask clocks, carets, video, rotating content, or fixture-controlled nondeterminism. Persist every ignored rectangle and its selector/provenance. Never infer ignored regions silently; an inferred mask could hide a real regression.

This enables useful conclusions:

- "`nav[role=navigation]` changed 2.1%; main content unchanged";
- "`CheckoutForm` bounds moved and its error-state region changed";
- "wide viewport changed only inside intended hero redesign";
- "unrelated footer region regressed."

`ImageDraw` can create rectangle/polygon masks; `ImageStat` accepts an image mask. Sources: [ImageDraw](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html), [ImageStat mask support](https://pillow.readthedocs.io/en/stable/reference/ImageStat.html#PIL.ImageStat.Stat).

Region metrics remain verification evidence, not design-quality scores. Review/intent logic decides whether change was intended and beneficial.

### P1: richer diff artifacts, isolated from measurement

Generate three artifact types:

1. **binary mask** — exact pixels passing configured tolerance;
2. **heat overlay** — threshold mask composited over the after image;
3. **contact sheet** — before, after, amplified delta, overlay, and optional 50% before/after blend at a reviewable common thumbnail size.

Also emit a changed-region crop when `getbbox()` returns a region. Avoid writing a meaningless crop for exact matches.

Use:

- `Image.point()` or `ImageEnhance.Contrast` for visible amplification;
- `ImageOps.autocontrast()` plus `ImageOps.colorize()` for an optional human-readable heatmap;
- `ImageDraw.rectangle()` for changed bounding boxes and semantic-region outlines;
- `ImageFilter.MaxFilter` only on the display copy to make isolated changed pixels visible;
- `ImageOps.contain()`/`pad()` only for contact-sheet layout;
- `Image.composite()`/`alpha_composite()` for overlays.

Never feed enhanced, blurred, dilated, annotated, cropped, or resized artifacts back into measurement. `ImageEnhance` and `ImageFilter` are presentation tools here, not regression logic. Sources: [ImageEnhance](https://pillow.readthedocs.io/en/stable/reference/ImageEnhance.html), [ImageFilter](https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html), [ImageDraw](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html), [Image.composite()](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.composite).

### P1: one versioned evidence manifest

Replace the desktop-only `diff_meta.json` contract with one atomic `visual-evidence.json` manifest:

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "uidetox_version": "...",
  "pillow_version": "...",
  "browser": {"name": "chromium", "version": "..."},
  "policy": {
    "pixel_threshold": 30,
    "alpha_background": "#ffffff",
    "dimension_policy": "strict",
    "color_policy": "record-or-srgb"
  },
  "captures": [
    {
      "url": "...",
      "viewport": {"name": "desktop", "width": 1280, "height": 800, "dpr": 1},
      "before": {"path": "...", "sha256": "...", "size": [1280, 4200], "mode": "RGB"},
      "after": {"path": "...", "sha256": "...", "size": [1280, 4200], "mode": "RGB"},
      "comparison": {
        "status": "complete",
        "changed_pixels": 0,
        "changed_ratio": 0.0,
        "changed_bbox": null,
        "rms": [0.0, 0.0, 0.0]
      },
      "regions": [],
      "artifacts": {}
    }
  ]
}
```

Also record:

- capture URL after redacting credentials/query secrets;
- requested versus resolved URL;
- page/source/runtime-map hash;
- capture time for both sides;
- original format/mode/dimensions;
- ICC presence/hash and alpha policy;
- before/after/diff artifact SHA-256;
- viewport, DPR, full-page flag, scroll height;
- errors and incomplete viewport pairs;
- intent/proposal/session identifier.

Freshness rule: `review`, `status`, `history`, and `finish` may consume evidence only if artifact hashes, current files, manifest schema, and intended capture session match. Missing or stale evidence must be explicit, not silently ignored.

Responsive desktop/mobile/tablet/wide pairs should share this same schema. Aggregate summaries should report maximum change and incomplete/error counts, never hide an individual viewport behind an average.

### P1: controlled PNG persistence

Keep JSON as canonical evidence. Optionally embed only a manifest ID and artifact hash into generated PNGs with `PngInfo`; do not duplicate the full manifest in PNG text.

PNG supports `pnginfo`, `compress_level`, `optimize`, ICC profile, and EXIF save options. `optimize=True` performs extra work and forces compression level 9. Default compression is adequate for capture-loop speed; make stronger compression an archival option, not a default. Source: [PNG save options](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#saving).

Generate clean output images rather than forwarding input metadata. Pillow's security guidance treats `image.info`, EXIF, ICC, and PNG text as untrusted and recommends stripping unneeded metadata. Source: [metadata security](https://pillow.readthedocs.io/en/stable/handbook/security.html#tampering).

## Feature disposition

| Pillow capability | Decision | Why |
| --- | --- | --- |
| `Image.open(..., formats=("PNG",))` | Adopt, P0 | Restricts parser surface; validates actual format. |
| `load()` + context manager | Adopt, P0 | Deterministic decode and file closure. |
| `verify()` | External import only | Requires reopening; redundant before mandatory pixel decoding. |
| `Image.MAX_IMAGE_PIXELS` and bomb warnings | Adopt, P0 | Memory/CPU defense. Never disable. |
| `ImageChops.difference()` | Keep, P0 | Correct absolute pixel-delta primitive. |
| `ImageChops.add()` + `point()` | Adopt, P0 | Fast threshold mask with current `> 30` semantics. |
| `ImageMath.lambda_eval()` | Defer | Safe expression API, but unnecessary for current diff; avoid feature-driven complexity. |
| `ImageMath.unsafe_eval()` | Prohibit | Executes Python `eval()`; no valid UIdetox need. |
| `histogram()` / `getbbox()` | Adopt, P0 | Fast count and changed-region bounds. |
| `ImageStat.Stat` | Adopt, P0 | Magnitude and region-level evidence. |
| alpha compositing / mode normalization | Adopt, P0 | Avoids false changes from discarded transparency semantics. |
| `ImageDraw` | Adopt, P0/P1 | Semantic masks and review annotations. |
| `ImageOps.exif_transpose()` | Imported baselines only | Irrelevant to native Playwright PNGs. |
| `ImageOps.fit()` / `pad()` / `contain()` | Contact sheets only | Resampling/cropping invalidates exact comparison. |
| `ImageCms` | Conditional, P1 | Useful only when ICC profiles differ; check LittleCMS availability. |
| `ImageEnhance` | Visualization only, P1 | Useful for reviewer visibility, not metrics. |
| `ImageFilter` | Visualization only, P2 | Dilation/blur may clarify display but corrupt measurement. |
| `PngInfo` | Minimal correlation metadata, P2 | Sidecar manifest is safer and easier to validate. |
| `compress_level` / `optimize` | Optional archival tuning | No functional benefit; `optimize` costs CPU. |
| `ImageFile.Parser` | Do not integrate | Designed for incremental byte streams; UIdetox reads completed local PNG files. Source: [ImageFile.Parser](https://pillow.readthedocs.io/en/stable/reference/ImageFile.html#PIL.ImageFile.Parser). |
| multiframe/APNG APIs | Reject input | Playwright evidence should be one deterministic frame. APNG adds timing/frame semantics UIdetox does not need. Source: [APNG sequences](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#apng-sequences). |
| `ImageSequence` | Do not integrate | Same reason as multiframe rejection. |
| `ImageGrab` | Do not integrate | Playwright already captures correct browser content and viewport state. |
| `ImageMorph` | Do not integrate | Morphology does not improve authoritative web regression evidence. |
| quantization/palette conversion | Do not use for metrics | Loses color precision; may be optional only for noncanonical preview size reduction. |
| entropy | Do not use as design quality | Visual entropy is not usability, craft, identity, or intent compliance. |
| NumPy/Arrow conversion | Do not add by default | Pillow-native path is sufficient; extra dependency and copies offer no current need. |
| arbitrary codecs/formats | Do not enable at app boundary | UIdetox capture contract is PNG; broader parsers expand attack surface. |

## Review and workflow integration

1. `uidetox capture --stage before` stores a `CaptureSet` with runtime elements and hashes.
2. `uidetox capture --stage after` stores matching captures and builds all viewport/page comparisons.
3. `uidetox review` validates manifest freshness, then exposes:
   - exact artifacts;
   - dimension mismatches;
   - per-viewport statistics;
   - top changed semantic regions;
   - intended/preserved-region violations.
4. `uidetox status` reports visual evidence as `fresh`, `stale`, `partial`, `failed`, or `missing`.
5. `uidetox history` snapshots the manifest summary and hashes.
6. executable loop requests fresh capture only when `dev_server` is configured/reachable; strict mode can require it.
7. `finish` can require fresh, complete evidence through `--require-visual-evidence` without making Pillow mandatory for all users.

Visual evidence should influence verification gates and reviewer context, not the objective anti-slop score directly. A complete redesign may correctly change most pixels; an unintended one-pixel overflow can be a serious regression.

## Determinism outside Pillow

Pillow cannot make nondeterministic screenshots comparable. Acquisition must first stabilize:

- same browser/build and device scale factor;
- same viewport and full-page policy;
- reduced motion and disabled/transitionally settled animations;
- fonts loaded;
- network/data fixtures stable;
- caret/cursor hidden;
- clock/random content controlled;
- same color scheme, locale, timezone, and authentication state;
- explicit capture-ready signal preferred over fixed sleep.

Consolidating through `runtime_observer` makes these inputs one shared contract instead of two divergent Playwright implementations.

## Tests required

### Unit

- identical RGB and RGBA images;
- alpha differences over declared background;
- changed count, ratio, RMS, extrema, and bbox;
- threshold boundary values;
- dimension mismatch without resampling;
- top-left visualization padding excluded from exact metrics;
- ICC equal/different/missing profiles;
- `DecompressionBombWarning` promoted to failure;
- corrupt, truncated, wrong-format, and multiframe rejection;
- context-managed closure;
- manifest schema and hash freshness;
- clean output metadata;
- Pillow-minimum compatibility.

### Integration

- `RuntimeObservation` screenshots + bounds -> semantic region metrics;
- one URL across all viewports;
- multiple pages with partial navigation/capture failures;
- before capture -> after capture -> manifest -> review;
- stale screenshot mutation invalidates review evidence;
- missing Pillow leaves non-capture UIdetox commands fully functional;
- responsive artifacts persist and appear in review/status/history.

### Performance

- native changed-pixel calculation remains materially faster than Python iteration;
- peak memory budget for longest supported full-page capture;
- sequential viewport processing releases image objects;
- contact-sheet/overlay generation never blocks canonical metrics persistence.

## P0-P3 roadmap

### P0: correctness, safety, speed

1. Create typed `visual_evidence.py` and versioned manifest schema.
2. Add safe PNG loader, resource limits, context-managed decode, explicit alpha/mode normalization, and strict geometry policy.
3. Replace Python iteration with `ImageChops.add()` + `point()` + histogram/getbbox/ImageStat.
4. Remove resize-to-match behavior.
5. Persist desktop/responsive/page evidence uniformly and atomically.
6. Add tests for corrupt/wrong-format/oversized/multiframe inputs, alpha, mismatch, threshold boundaries, and exact metrics.
7. Raise/test the Pillow minimum to `12.3.0`, then delete the Python pixel loop and its legacy `getdata()` compatibility branch in favor of the Pillow-native mask pipeline.

### P1: architectural and semantic integration

1. Consolidate capture acquisition through `runtime_observer`.
2. Add semantic-region and explicit ignore masks from `RuntimeElement.bounds`.
3. Enforce manifest hash/freshness validation in review/status/history/finish.
4. Connect page/region evidence to frontend-map ownership and intent/preserve contracts.
5. Add strict CLI/config controls: tolerance, pixel limit, dimension policy, color policy, and `--require-visual-evidence`.

### P2: reviewer experience

1. Add clean heat overlay, changed crop, 50% blend, and contact sheet.
2. Add conditional ICC-to-sRGB normalization for imported/cross-machine baselines, with cached transforms and clear fallback when LittleCMS is unavailable.
3. Surface top changed semantic regions and incomplete viewports in review prompts and terminal/JSON status.
4. Add archival compression controls; keep fast ordinary PNG compression as default.

### P3: optional future work

1. Isolate untrusted external-baseline processing in a constrained subprocess if UIdetox becomes a service accepting uploads.
2. Add intentional animation-frame evidence only if product scope expands beyond deterministic screenshots; otherwise keep APNG/multiframe rejected.
3. Evaluate a separate perceptual metric library only if exact/masked RGB evidence proves insufficient. Pillow does not supply SSIM or semantic quality judgement.

## Bottom line

Pillow should remain. Current use proves the dependency's value but captures only a fraction of the useful integration. Best expansion is not broad image editing. It is a narrow visual-evidence engine: safe PNG decode, deterministic normalization, fast masks/statistics, semantic-region attribution, clean reviewer artifacts, and hash-validated provenance across every page and viewport.

## Primary sources

- [Pillow Image module](https://pillow.readthedocs.io/en/stable/reference/Image.html)
- [File handling in Pillow](https://pillow.readthedocs.io/en/stable/reference/open_files.html)
- [Pillow security](https://pillow.readthedocs.io/en/stable/handbook/security.html)
- [Pillow concepts and modes](https://pillow.readthedocs.io/en/stable/handbook/concepts.html)
- [ImageChops](https://pillow.readthedocs.io/en/stable/reference/ImageChops.html)
- [ImageMath](https://pillow.readthedocs.io/en/stable/reference/ImageMath.html)
- [ImageStat](https://pillow.readthedocs.io/en/stable/reference/ImageStat.html)
- [ImageOps](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html)
- [ImageDraw](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html)
- [ImageEnhance](https://pillow.readthedocs.io/en/stable/reference/ImageEnhance.html)
- [ImageFilter](https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html)
- [ImageCms](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html)
- [Pillow feature detection](https://pillow.readthedocs.io/en/stable/reference/features.html)
- [ImageFile and incremental parser](https://pillow.readthedocs.io/en/stable/reference/ImageFile.html)
- [PNG/APNG format documentation](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#png)
- [Pillow Python support](https://pillow.readthedocs.io/en/stable/installation/python-support.html)
- [Pillow 10.3.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/10.3.0.html)
- [Pillow 12.1.0 release notes](https://pillow.readthedocs.io/en/stable/releasenotes/12.1.0.html)
