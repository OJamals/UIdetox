# Programmatic rendered-layout detection

Research date: 2026-07-20

## Decision

UIdetox should keep its Playwright runtime observer as the primary detector and
extend it with peer-relative geometry, direct text-node measurements, font
readiness/metrics, and ancestor clipping calculations.

No maintained GitHub project found in this survey directly identifies all of
the following as semantic, selector-attributed findings:

- layout misalignment
- font or baseline misalignment
- truncated or clipped text and components
- text touching a card or control edge
- improper horizontal or vertical padding
- inadequate spacing between lines

Visual-regression tools detect changed pixels, but they need a trusted baseline
and cannot explain whether the change represents bad padding, a deliberate
redesign, or an unrelated rasterization difference. They are best used as a
second evidence layer.

Recommended order:

1. Harden UIdetox's existing DOM and computed-style measurements.
2. Borrow Galen's relational layout vocabulary for explainable rules.
3. Add browser-native text shaping and font-readiness evidence, borrowing ideas
   from Pretext where useful.
4. Add a stable screenshot-diff layer using Pixelmatch-style local diff density
   or an optional ODiff adapter.
5. Use OCR/computer vision only for opaque surfaces such as canvas, embedded
   images, or screenshot-only inputs.

## What can be detected objectively

Some requested defects have a direct browser signal. Others require a design
reference or peer consensus.

| Defect | Strong programmatic evidence | Important qualification |
| --- | --- | --- |
| Truncated text | Text-node `Range` rectangles outside the effective clipping rectangle; `scrollWidth > clientWidth`; `scrollHeight > clientHeight`; active `line-clamp` | Scroll overflow may be intentional |
| Clipped component | Descendant rectangle outside the intersection of all clipping ancestors | Portals, transforms, menus, and deliberate bleed need exemptions |
| Text touching an edge | Minimum distance from direct text rectangles to the element's inner border box | Icons and nested labels must not pollute the text union |
| Uneven padding | Logical start/end and block-start/end inset differences; deviation from equivalent peers or tokens | Asymmetry may be intentional |
| Layout misalignment | Edge, center, or baseline outlier among equivalent peers in the same visual row/column | An absolute offset alone does not prove misalignment |
| Font misalignment | Loaded-font status, peer font mismatch, line-box/baseline deviation, font ascent/descent evidence | The bottom of a text rectangle is not a true typographic baseline |
| Inadequate line spacing | Actual line rectangles overlap, glyph boxes approach adjacent lines, or line-height is an outlier from equivalent text | A universal line-height ratio is a heuristic, not proof |

The detector should label evidence accordingly:

- `objective`: clipping, overlap, or content outside an effective clip box
- `peer-relative`: a robust outlier among equivalent components
- `token-relative`: a mismatch against an explicit design-system value
- `heuristic`: an absolute threshold without a peer, token, or baseline
- `regression`: a change from an accepted screenshot or geometry baseline

## GitHub candidates

Maintenance observations below use repository state checked on the research
date.

### 1. Playwright: retain as the measurement and capture engine

Repository: [microsoft/playwright](https://github.com/microsoft/playwright)
License: Apache-2.0
Status: active; repository activity was current on 2026-07-19

Playwright already gives UIdetox the correct execution context: the final DOM,
computed styles, loaded browser fonts, viewport, device scale, and rendered
geometry. UIdetox can evaluate `getBoundingClientRect`,
`Range.getClientRects`, `scrollWidth`/`clientWidth`, CSS overflow, and
`document.fonts` in one page evaluation.

Playwright's own
[visual comparison documentation](https://github.com/microsoft/playwright/blob/main/docs/src/test-snapshots-js.md)
also supplies useful capture practices: obtain stable consecutive frames,
control volatile content with injected styles, and keep the rendering
environment consistent. Those practices should be borrowed for UIdetox's
Python capture path; adopting the JavaScript Playwright Test runner is
unnecessary.

Verdict: **use directly and deepen**.

### 2. Galen Framework: borrow the relational rule model

Repository: [galenframework/galen](https://github.com/galenframework/galen)
License: Apache-2.0
Status: not archived, but the last repository push was in 2022 and the latest
GitHub release shown was from 2019

Galen's useful idea is not its Java/Selenium runtime. It is its vocabulary for
describing layout relationships:

- `inside`
- `near`
- `above` / `below`
- `left of` / `right of`
- `aligned horizontally` / `aligned vertically`
- `centered`
- width and height relationships
- device- or viewport-specific conditions

The [README examples](https://github.com/galenframework/galen#how-does-it-work)
show that relative locations and dimensions produce clearer layout checks than
isolated absolute coordinates.

UIdetox can express the same concepts as typed findings over captured DOM
rectangles, without adding Java, Selenium, or Galen's specification language.

Verdict: **borrow the rule semantics; do not add the runtime dependency**.

### 3. Pretext: useful text-fit and line-layout algorithms

Repository: [chenglou/pretext](https://github.com/chenglou/pretext)
License: MIT
Status: active; repository activity was current in June 2026

Pretext is a TypeScript multiline text measurement and layout engine. It uses
the browser's font engine through canvas measurement, then performs cached line
breaking and exposes paragraph height, line count, maximum line width, and line
ranges. Its documented use cases include verifying that button labels do not
wrap or overflow.

Relevant ideas for UIdetox:

- use `Intl.Segmenter` rather than naïvely splitting text
- measure with the resolved browser font
- retain per-line ranges and widths
- account for letter spacing, white-space behavior, word breaking, CJK, emoji,
  and bidirectional text
- cache prepared text measurements across viewports

Pretext is not a complete CSS inline-formatting implementation. Its README
calls out limitations around `system-ui` accuracy on macOS, variable-font
features, and unsupported CSS text features. It also lives in the JavaScript
ecosystem while UIdetox's CLI is Python.

The immediate implementation should therefore use browser-native
`Range.getClientRects`, `CanvasRenderingContext2D.measureText`, and
`document.fonts`; Pretext can be evaluated later as an injected optional engine
if multilingual line breaking proves hard to reproduce.

Verdict: **borrow now; prototype before adopting**.

### 4. Pixelmatch: best small visual corroboration source

Repository: [mapbox/pixelmatch](https://github.com/mapbox/pixelmatch)
License: ISC
Status: active; repository activity was current in July 2026

Pixelmatch is a small dependency-free pixel comparison library with perceptual
color comparison and anti-alias detection. Its current API also supports a
local window-density result: instead of failing on sparse raster noise across
an entire page, a caller can detect a concentrated patch of changed pixels.

That model fits UIdetox better than a page-wide mismatch percentage:

1. compare accepted and current screenshots in a deterministic environment
2. find dense local diff regions
3. intersect each region with captured DOM/text rectangles
4. raise confidence when the image region and a semantic DOM finding agree
5. report unmatched image differences as unclassified visual regressions

Pixelmatch still cannot say why pixels changed and requires same-sized images.
It should not gate layout quality without DOM evidence or an accepted baseline.

Verdict: **best algorithm to borrow or expose through a small adapter**.

### 5. ODiff: optional high-throughput screenshot adapter

Repository: [dmtrKovalenko/odiff](https://github.com/dmtrKovalenko/odiff)
License: MIT
Status: active; release 4.3.8 was published in April 2026

ODiff is a native Zig/SIMD image comparison tool with a CLI, Node binding, and
persistent newline-JSON server. It supports anti-alias handling, ignored
regions, perceptual thresholds, changed scanlines, and a distinct
`layout-diff` result when image dimensions differ.

It is attractive when UIdetox must process many large, full-page captures. It
does not add semantic classification, and shipping platform binaries adds
packaging complexity.

Verdict: **optional adapter after the semantic DOM layer is mature**.

### 6. LooksSame: useful diff clustering

Repository: [gemini-testing/looks-same](https://github.com/gemini-testing/looks-same)
License: MIT

LooksSame supplies perceptual comparison, anti-alias and caret handling, diff
bounds, and diff clusters. Clusters are more useful than a single total mismatch
count because UIdetox can map each cluster to selectors and runtime findings.

Its Node runtime and overlap with Pixelmatch make it a secondary choice. Its
clustering approach is worth borrowing if UIdetox's existing image evidence
does not already provide connected regions.

Verdict: **borrow clustering ideas; no immediate dependency**.

### 7. Visual Regression Tracker: optional evidence management

Repository:
[Visual-Regression-Tracker/Visual-Regression-Tracker](https://github.com/Visual-Regression-Tracker/Visual-Regression-Tracker)
License: Apache-2.0
Status: active; repository activity was current in July 2026

Visual Regression Tracker is a self-hosted service for storing baselines,
reviewing image differences, retaining history, and ignoring volatile regions.
It can use Pixelmatch, LooksSame, or ODiff and accepts results through a REST
API.

This solves review and baseline management, not defect classification. Requiring
Docker and a service would conflict with UIdetox's lightweight local scan path.

Verdict: **possible future integration, not a core detector**.

### 8. UIED and OCR: fallback for opaque surfaces only

Repositories:

- [MulongXie/UIED](https://github.com/MulongXie/UIED), Apache-2.0
- [tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract),
  Apache-2.0
- [naptha/tesseract.js](https://github.com/naptha/tesseract.js), Apache-2.0
- [PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR),
  Apache-2.0

UIED combines OCR text boxes with computer-vision component detection and emits
GUI element geometry. Tesseract can emit hOCR, TSV, ALTO, and PAGE outputs with
text positions. PaddleOCR provides text and layout coordinates.

These tools can recover approximate text and component rectangles when the
content is painted into canvas, embedded in an image, or supplied only as a
screenshot. They are a poor default for ordinary web pages:

- installation and model cost are much higher
- small antialiased UI text produces more recognition/box errors
- DOM ownership and source mapping are lost
- OCR cannot infer intended padding or line height
- UIED's documented stack and tuning requirements are old

Verdict: **explicit opt-in fallback for opaque regions only**.

## Projects not recommended for adoption

| Project | Reason |
| --- | --- |
| [lost-pixel/lost-pixel](https://github.com/lost-pixel/lost-pixel) | The repository was archived on 2026-04-22. Its responsive capture and masking workflow remains useful prior art. |
| [garris/BackstopJS](https://github.com/garris/BackstopJS) | A broad regression harness that duplicates UIdetox's browser/capture orchestration; repository activity and release metadata are stale/inconsistent. |
| [rsmbl/Resemble.js](https://github.com/rsmbl/Resemble.js) | The project describes itself as being in low-maintenance mode and overlaps better-maintained diff engines. |
| [foliojs/fontkit](https://github.com/foliojs/fontkit) | Useful for inspecting font-file ascent, descent, line gap, glyph bounds, shaping, and fallback coverage, but font-file metrics are not proof of the browser's final rendered layout. |

## Proposed UIdetox detector

### Capture stage

For every configured viewport and relevant UI state:

1. wait for `document.fonts.ready`
2. record failed or unresolved `document.fonts.check(...)` results
3. disable animations, transitions, carets, and volatile content
4. wait until two consecutive DOM-geometry snapshots are stable
5. capture device scale, browser version, platform, locale, zoom, writing mode,
   and font availability with the evidence
6. gather direct text-node ranges instead of selecting all descendant content
7. retain each line rectangle, not only their union
8. gather every clipping ancestor and calculate the effective intersection
9. preserve transforms and logical writing direction in the measurement model

### Layout and spacing classification

Build visual peer groups using:

- common parent and layout context
- semantic role and tag
- similar size and computed typography
- overlap on the row or column axis
- grid track or wrapped-flex membership
- repeated component signature from the frontend map

For each peer group, compute left, right, top, bottom, center, and text-baseline
anchors. Use the median and median absolute deviation rather than a single
fixed tolerance. A finding should require:

- at least three peers
- two or more peers that form a tight consensus
- one clear outlier
- no explicit exception such as absolute positioning, transform, deliberate
  asymmetric token, or responsive reordering

Borrow Galen's relational terms for finding codes and messages. For example:

- `not-aligned-block-center`
- `not-aligned-inline-start`
- `unexpected-gap-after`
- `outside-clipping-ancestor`
- `not-centered-inside-control`

### Text and font classification

For each direct text run:

1. wait for and record the resolved font
2. build a complete canvas font shorthand from computed styles
3. call `measureText` and retain `actualBoundingBoxAscent`,
   `actualBoundingBoxDescent`, width, and available font bounding-box fields
4. group `Range.getClientRects()` into lines using writing-mode-aware
   coordinates
5. compare observed line advances with computed line-height and font metrics
6. compare equivalent peers' resolved family, size, weight, letter spacing,
   line-height, first-line position, and glyph-box center

Do not treat `Range` rectangle bottoms as true baselines. Flag baseline
misalignment only when peer geometry and font metrics agree, or mark it as a
lower-confidence heuristic.

Line spacing should be an error when adjacent glyph or line boxes overlap or
are clipped. A low `line-height / font-size` ratio without overlap should
remain a warning unless it violates an explicit design token or peer consensus.

### Clipping and edge-contact classification

For text:

- compare every direct text line rectangle to the intersection of the element,
  padding box, and clipping ancestors
- detect `line-clamp`, `text-overflow`, fixed block sizes, and hidden/clip
  overflow separately
- distinguish deliberate ellipsis from accidental clipping
- record which edge and how many pixels are lost

For components:

- compare each visible descendant rectangle against every effective clipping
  ancestor
- ignore descendants rendered through portals
- distinguish scroll containers from hidden/clip containers
- account for transforms and deliberate decorative bleed

For edge contact and padding:

- use the nearest direct text rectangle, not the union of nested descendants
- measure logical inline-start/end and block-start/end
- prefer explicit design tokens, then equivalent-peer consensus
- use absolute minimums only as configurable fallback heuristics
- treat buttons, chips, inputs, cards, and free-form regions as separate
  component classes

### Optional screenshot corroboration

Add visual evidence only after semantic measurement:

1. capture stable accepted/current images in the same environment
2. mask known dynamic selectors
3. run anti-alias-aware comparison
4. calculate local diff density and connected diff clusters
5. intersect clusters with selector rectangles
6. increase confidence for matching DOM findings
7. store unmatched clusters as unclassified regressions for review

This preserves UIdetox's explainability and source attribution while still
catching raster-only failures, pseudo-elements, icons, shadows, and font
rendering changes.

## Suggested implementation sequence

1. **Direct text geometry:** measure only text nodes and retain per-line boxes.
2. **Effective clip rectangles:** intersect all clipping ancestors and add
   explicit line-clamp/ellipsis evidence.
3. **Peer model:** extend flex-only peers to grid tracks, wrapped flex rows, and
   repeated component signatures; use median absolute deviation.
4. **Logical spacing:** support RTL and vertical writing modes; compare against
   tokens or peer consensus before absolute thresholds.
5. **Font evidence:** add font readiness and canvas text metrics; downgrade
   baseline claims that rely only on range bottoms.
6. **Stable capture:** require stable consecutive geometry and screenshot
   frames while animations and carets are disabled.
7. **Visual corroboration:** prototype Pixelmatch-style window density and
   region-to-selector attribution.
8. **Opaque-surface adapter:** add OCR/CV only if real canvas or screenshot-only
   targets justify the dependency.

## Validation corpus

Before promoting these checks into the score, build labeled fixtures covering:

- flex rows, flex columns, wrapping, grid, tables, inline flow, and transforms
- clipping on the element and on multiple ancestors
- intentional ellipsis versus accidental truncation
- cards with nested icons, badges, labels, and pseudo-elements
- symmetric and deliberately asymmetric padding
- headings, body text, buttons, chips, and mixed-font inline runs
- local fonts, delayed web fonts, failed fonts, fallbacks, and variable fonts
- Latin, Arabic/RTL, CJK, emoji, and combining marks
- browser zoom and device scale factors
- Chromium, Firefox, and WebKit at mobile and desktop viewports

Measure precision and recall per finding code. Do not tune only to synthetic bad
examples: include intentional asymmetry, compact controls, scroll containers,
overlays, marquees, code blocks, and decorative overflow as negative controls.

The acceptance target should be high precision first. A lower-confidence
finding can still be useful in a review brief, but objective clipping findings
and high-confidence peer outliers are the only suitable automatic gates.
