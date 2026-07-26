# Design Evidence Model

## Status

Accepted.

## Context

Source tokens and utility-class names do not prove the colors, geometry, state,
or stacking that a browser renders. Static pairing heuristics therefore created
false confidence and false positives, while the runtime observer already owned
the authoritative computed DOM evidence.

## Decision

Rendered design quality uses the existing runtime capture and frontend map:

- One DOM evaluation per captured scenario state collects computed paint,
  geometry, interaction state, theme, focus, occlusion, and explicit sibling
  equivalence evidence.
- The existing `RuntimeElement.measurements` field carries those facts. The
  existing frontend graph persists them and derives containment and equivalence
  edges; no parallel artifact, graph, or retained cache is introduced.
- Pure cross-element policy consumes a `RuntimePage` and emits immutable
  findings. Policy does not query the DOM or mutate capture evidence.
- Contrast is evaluated from the captured foreground and ordered ancestor
  backdrop stack after alpha compositing. Modern browser color formats are
  normalized to linear sRGB. Large text uses the WCAG 2.2 CSS-pixel boundaries:
  24px normal or 18.6667px at weight 700.
- Gradients, images, blending, filters, translucent unresolved backdrops, and
  other unproven paint effects produce an explicit unresolved-coverage finding.
  Unknown paint is never treated as a passing contrast result.
- Component and palette drift require captured equivalence provenance. Visual
  similarity or class-name resemblance alone is insufficient.
- Focus validity is re-derived from baseline and focused computed styles. A
  background, border, outline, or shadow must produce a perceptible contrast
  delta; raw visibility booleans do not qualify. Target-spacing exceptions use
  the WCAG 24 CSS-pixel circle centered on an undersized target, tested against
  a neighboring target's circle or rectangle as appropriate.
- Subjective A/B/C/D review must cite findings and semantic regions and cover
  the exact completed route/state/viewport tuples, including non-Cartesian
  capture matrices. A deterministic matrix digest is persisted and rechecked
  during scoring and finalization. Incomplete review cannot affect the
  displayed score. A pending critical deterministic finding prevents
  subjective input from lifting the blended score above the objective score.

## Consequences

Static analysis still inventories colors and detects unrelated source
anti-patterns, but it no longer guesses WCAG pairings from stylesheet token
names or Tailwind classes. Browser capture costs modestly more per selected
element; expensive paint and equivalence work remains bounded by the existing
DOM budget and is computed only for emitted elements. Unsupported paint effects
remain visible as evidence gaps for a reviewer or a later specialized renderer.
