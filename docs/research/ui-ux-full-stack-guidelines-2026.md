# Validated UI/UX and full-stack engineering guidance

Research date: 2026-08-03

## Decision

UIdetox should retain its anti-slop design opinion, but it should stop presenting
taste preferences, static risk heuristics, measured defects, and standards
violations as one kind of finding. The next rules revision should classify each
rule by evidence basis and only use compliance language when the available
evidence proves the applicable requirement and its exceptions.

The current authoritative baselines are:

- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) for accessibility conformance. WCAG
  2.2 is the current W3C Recommendation; 4.1.1 Parsing is obsolete and removed.
- the [HTML Living Standard](https://html.spec.whatwg.org/) and applicable W3C
  CSS specifications for native semantics, forms, focus, directionality, media
  preferences, responsive layout, and input;
- [Core Web Vitals](https://web.dev/articles/defining-core-web-vitals-thresholds)
  for user-experience performance: LCP at or below 2.5 seconds, INP at or below
  200 milliseconds, and CLS at or below 0.1, evaluated at the 75th percentile;
- [OpenAPI 3.2.0](https://spec.openapis.org/oas/v3.2.0.html), published
  2025-09-19, as the latest OpenAPI specification;
- [HTTP Semantics, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html),
  [Problem Details, RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html), and
  [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) for wire-contract
  behavior;
- the [OWASP Top 10:2025](https://owasp.org/www-project-top-ten/) and current
  OWASP cheat sheets for web security review;
- [OpenTelemetry semantic conventions 1.43.0](https://opentelemetry.io/docs/specs/semconv/)
  and [W3C Trace Context](https://www.w3.org/TR/trace-context/) for
  cross-layer observability.

No automated UIdetox result should claim full WCAG conformance. W3C states
that tools cannot check every accessibility aspect and that knowledgeable human
evaluation remains necessary. Source: [Selecting Web Accessibility Evaluation
Tools](https://www.w3.org/WAI/test-evaluate/tools/selecting/).

## Local baseline inspected

The canonical codebase-memory graph and current source show:

- 217 static analyzer rules in `uidetox/analyzer_rules.py`;
- custom analyzer seams for accessibility, document structure, CSS, HTML,
  React, browser security, interaction, and runtime patterns in
  `uidetox/analyzer_custom.py`;
- runtime findings for layout and font misalignment, chart baselines, text
  collisions and separation, text/component clipping, concealed scroll
  actions, navigation-choice overload, edge contact, horizontal/vertical
  padding, pathological wrapping, and line spacing in
  `uidetox/runtime_layout.py`;
- runtime capture of roles, accessible names, focus styles, bounds, computed
  layout/type/color, screenshots, URLs, states, and viewports in
  `uidetox/runtime_observer.py`;
- canonical experience-state planning in `uidetox/experience_states.py` and
  `uidetox/redesign.py`;
- source-backed operation, request, response, error, status, auth, service, and
  entity lineage in `uidetox/contract_adapters.py` and
  `uidetox/contract_graph.py`;
- exact root/bundled parity for `AGENTS.md`, `SKILL.md`, `commands/`, and
  `reference/` at research time.

Strength is source-aware remediation: findings can retain source anchors,
runtime anchors, contract evidence, provenance, confidence, and freshness.
Primary gap is not rule count. It is evidence precision and missing coverage at
standards boundaries.

## Required evidence classes

Every rule or recommendation should belong to exactly one class:

1. **Normative** — directly testable requirement from a named standard. Report
   applicable level, exceptions, evidence, and source.
2. **Measured** — quantitative browser, network, image, API, or DB observation.
   Report environment, sample, threshold policy, and uncertainty.
3. **Heuristic** — risk signal requiring confirmation. Never label it a WCAG,
   security, performance, or contract failure by itself.
4. **Review** — taste, clarity, brand, information architecture, perceived
   quality, or context-dependent UX judgment.

This can be metadata on the existing rule/finding model. Do not create a
parallel issue schema or second lifecycle vocabulary. Existing source,
runtime, contract, status, freshness, and provenance authorities remain
canonical.

## Corrections, consolidation, and removals

| Current rule or guidance | Problem | Validated replacement |
|---|---|---|
| `COLOR_BLACK_SLOP`, `CSS_PURE_BLACK_SLOP`, `PURE_BLACK_TEXT_SLOP`; blanket bans on pure black/white/gray | Duplicate taste rules; color value alone says nothing about accessibility. Forced-color and user-contrast preferences also invalidate a universal palette prescription. | Consolidate as one optional anti-slop review signal. Accessibility uses measured text/non-text contrast in every relevant state and preserves forced colors. [WCAG non-text contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast), [Media Queries 5 user preferences](https://www.w3.org/TR/mediaqueries-5/#mf-user-preferences). |
| `COLOR_GRADIENT_SLOP`, `CSS_GRADIENT_SLOP`, `TAILWIND_V4_GRADIENT_SLOP`, gradient-text/border variants | Overlapping syntax detectors mix brand taste with contrast claims. | Share one gradient fact extractor; emit separate context-aware review rules. Only measured contrast or obscured content is normative. |
| `TYPOGRAPHY_SLOP`; serif/system-font bans; prescribed font pairings | Font family is not a compliance result. Extra web fonts can delay text and shift layout. Global font bans are hostile to language coverage and brand intent. | Human review for distinctiveness; deterministic checks for fallback coverage, loading, missing glyphs, text clipping, user zoom, and spacing override. Measure font-induced LCP/CLS. [web.dev font guidance](https://web.dev/articles/font-best-practices), [WCAG text spacing](https://www.w3.org/WAI/WCAG22/UNDERSTANDING/text-spacing.html). |
| `HARDCODED_PX_FONT_SLOP`: all pixel font sizes “break accessible scaling” | False as a universal claim; browser zoom scales CSS pixels. Root/body sizing can override user defaults, but isolated `px` usage does not prove failure. | Keep the narrower `ABSOLUTE_FONT_SIZE_BODY_SLOP`; prove 200% resize and 400%/320-CSS-pixel reflow in-browser. [WCAG Reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html). |
| `UGLY_SCROLLBAR_SLOP` recommends hiding scrollbars | Hidden scrollbars can remove affordance and conflict with keyboard, touch, forced colors, and target-size needs. | Remove “hide” remediation. Preserve native scroll affordance; customize only with measured contrast, size, input, and discoverability checks. |
| `MISSING_HOVER_STATES` and blanket transition requirements | Touch and pen do not guarantee hover. A transition is not required and may add unwanted motion. | Require operability and state communication across keyboard/pointer paths; treat hover polish as review-only. Query `hover`/`pointer` only for progressive enhancement. [Media Queries 5](https://www.w3.org/TR/mediaqueries-5/), [Pointer Events 3](https://www.w3.org/TR/pointerevents3/). |
| `FOCUS_VISIBLE_MISSING_SLOP`: `:focus` without `:focus-visible` “over-triggers” | Dangerous: `:focus` can be valid and visible focus is required. Absence of `:focus-visible` is not a failure. | Detect removed/imperceptible/obscured focus, not selector preference. Measure author focus contrast and visibility after keyboard traversal. [Focus Not Obscured](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum), [Focus Appearance](https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance). |
| `AUTOFOCUS_SLOP` blanket rejection | Initial focus is context-dependent; native modal dialogs require deliberate focus placement. | Heuristic only. Review whether focus change is expected, announced, reversible, and preserves logical order. [HTML dialog guidance](https://html.spec.whatwg.org/multipage/interactive-elements.html#the-dialog-element). |
| `TOUCH_TARGET_SLOP` assumes 44 px | 44 by 44 CSS pixels is WCAG 2.5.5 AAA. WCAG 2.5.8 AA is 24 by 24 with spacing, equivalent-control, inline, UA, and essential exceptions. | Add exact 24-CSS-pixel/spacing-aware AA runtime detector; retain 44 px as explicitly labeled AAA/enhancement review. [Target Size Minimum](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum), [Target Size Enhanced](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced). |
| `VIDEO_NO_CAPTIONS` passes on any `<track>` | Presence of an arbitrary track does not prove captions, correct language, valid cues, synchronization, or equivalent content. | Static candidate check requires `kind="captions"`; runtime/manual evidence validates availability, correctness, synchronization, and prerecorded/live applicability. |
| `SCROLL_SNAP_WITHOUT_BEHAVIOR_SLOP` recommends smooth scrolling | Smooth scrolling is not required and can worsen motion sensitivity. | Remove requirement. Validate keyboard/pointer reachability, snap escape, focus visibility, and reduced-motion behavior. |
| “Animate only transform and opacity”; “always spring”; forced stagger, perpetual, or magnetic motion | Performance preference presented as universal design law. Some functional motion changes size/position; blanket animation adds work and accessibility risk. | Prefer compositor-friendly properties when measured, but gate all non-essential motion on user preference and purpose. Keep motion appropriateness in human review. [Media Queries reduced motion](https://www.w3.org/TR/mediaqueries-5/#prefers-reduced-motion), [Optimize INP](https://web.dev/articles/optimize-inp). |
| “Skeletons, never spinners”; “validate on blur, not keystroke” | Context-dependent patterns stated as rules. Skeletons can misrepresent unknown shape; delayed validation can waste effort; eager validation can be noisy. | Review timing against task, latency, error cost, assistive-tech announcements, and evidence. Require concise, associated, actionable feedback, not one universal widget/timing. [WAI form notifications](https://www.w3.org/WAI/tutorials/forms/notifications/). |
| `MISSING_DARK_MODE`: every light surface needs a dark variant | No standard requires every product to offer dark mode. Partial theme support is harmful, but a single intentional theme can be valid. | If theme support is claimed or detected, test completeness and `prefers-color-scheme`; otherwise treat dark mode as product intent. |
| `HARDCODED_BREAKPOINT_SLOP` recommends CSS custom properties in media queries | Generic `var()` values are not a portable media-query token mechanism. Pixel breakpoints are not inherently defective. | Detect duplicated/inconsistent breakpoints and component breakage. Prefer content-derived media queries or container queries where ownership demands them. [CSS Containment 3](https://www.w3.org/TR/css-contain-3/). |
| `DANGEROUS_HTML_SLOP`/`INNER_HTML_ASSIGN_SLOP` accept presence of `DOMPurify` as safety evidence | Token presence does not prove the value was sanitized at the sink, correct configuration, safe post-sanitize handling, or current dependency. | Trace untrusted source to context-specific sink. Prefer safe sinks; when HTML is required, prove sanitizer call, policy/config, no unsafe mutation afterward, and dependency provenance. [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html). |
| Full-stack rule: “never duplicate types; shared package preferred” | Backend entities, API DTOs, and frontend view models have different responsibilities. A shared runtime package can create coupling; generated clients can still duplicate representations intentionally. | Require one declared wire-contract authority plus traceable generated/manual projections. Compare semantics and provenance, not identical source declarations. |
| Full-stack rule: every API URL comes from environment config | Relative same-origin URLs are valid and often safer. Environment variables do not make client-exposed data secret. | Detect hardcoded environment-specific origins, not stable relative routes. Classify config as public/client or server-only; scan built artifacts for secrets. [OWASP Security Misconfiguration](https://owasp.org/Top10/2025/A02_2025-Security_Misconfiguration/). |
| DB rules require nullable columns and enums to map directly to UI types/options | Leaks persistence schema through service/API boundaries; UI may intentionally expose a filtered enum subset or a normalized non-null DTO. | Enforce DB-to-service-to-DTO-to-client lineage. Compare each boundary contract and preserve authorization/context filtering. Unknown future enum values need explicit handling. |
| “ISO 8601 preferred” | Too vague for a deterministic wire rule; dates, instants, local date-times, durations, and zones have different semantics. | Record semantic type. For Internet timestamps, use a declared RFC 3339 profile and retain offset/zone intent where needed. [RFC 3339](https://www.rfc-editor.org/rfc/rfc3339.html). |
| All backend validation errors must be inline | Cross-field, form-level, authorization, conflict, and service errors may not map to one field. | Inline field-addressable errors; also provide accessible summary/global status and preserve typed problem identity. |
| All 401/403 responses redirect to login | Incorrect HTTP semantics. 401 concerns missing/invalid credentials and includes a challenge; 403 can mean valid but insufficient credentials. Redirecting 403 can loop or destroy context. | Map 401 to reauthentication/session recovery when appropriate; map 403 to a stable forbidden state with allowed recovery. [RFC 9110 authentication semantics](https://www.rfc-editor.org/rfc/rfc9110.html#name-authentication). |

Root and `uidetox/data/` copies are deliberate package assets, not orphaned
duplicates. Keep exact parity and one owning update/copy verification path;
never delete the bundled copies required by the wheel.

## Coverage to add or deepen

### Accessibility

Deterministic or browser-measurable additions:

- WCAG 2.2 AA target size with all spacing and semantic exceptions;
- keyboard traversal, unexpected focus traps, positive `tabindex`, focus order,
  visible focus, and focus obscured by sticky/overlay content;
- text contrast and component/state contrast against actual composited adjacent
  colors, including hover, focus, selected, disabled, error, and forced-colors;
- accessible name/role/value parity with visible labels; prefer native HTML
  before ARIA. ARIA roles promise matching keyboard behavior. Source:
  [WAI-ARIA APG Read Me First](https://www.w3.org/WAI/ARIA/apg/practices/read-me-first/);
- heading/landmark structure without requiring one fixed page template;
- 320-CSS-pixel reflow, 200% text resize, 400% zoom, orientation, text-spacing
  overrides, and no loss/clipping after font substitution;
- pause/stop/hide for moving or updating content, reduced motion, flashing
  thresholds, dragging alternatives, pointer cancellation, and label-in-name;
- dynamic status messages that expose waiting, progress, results, success, and
  errors without stealing focus or producing chatty duplicate live regions.
  Source: [WCAG Status Messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages).

Human/assistive-technology review remains required for alternative-text
quality, reading order meaning, captions/audio descriptions, accessible names
in context, cognitive load, keyboard interaction conventions for custom
widgets, and browser/screen-reader/mobile combinations.

### Responsive, input, and device behavior

- Run scenarios at content-driven widths plus 320-CSS-pixel reflow, zoom,
  portrait/landscape, coarse/fine pointer, hover/no-hover, reduced motion,
  contrast preferences, forced colors, and text expansion.
- Capture `dvh`/`svh`/`lvh` behavior when browser chrome or virtual keyboards
  change the visible viewport. The CSS specification distinguishes large,
  small, and dynamic viewport units. Source: [CSS Values and Units 4](https://www.w3.org/TR/css-values-4/#viewport-relative-lengths).
- Prefer Pointer Events for shared mouse/touch/pen behavior; device-specific
  branches require evidence. Source: [Pointer Events 3](https://www.w3.org/TR/pointerevents3/).
- Test container-owned components inside multiple host widths. Do not infer
  responsiveness from the presence of media/container-query syntax.
- Check safe-area and virtual-keyboard occlusion only on applicable devices;
  treat device emulation as lab evidence, not a substitute for representative
  hardware.

### Content, navigation, and UX states

Keep the existing canonical experience-state vocabulary as owner. Extend it
only through a measured schema migration; do not introduce a second status
model. Coverage analysis should distinguish:

- user-visible initial, loading, empty, error, success, disabled, and first-run
  states already modeled;
- authentication-required versus forbidden;
- offline, timeout, retrying, cancelled, partial/stale data, rate-limited, and
  conflict outcomes where the mapped transport contract proves applicability;
- optimistic mutation pending, rollback, duplicate submission, and recovery;
- background refresh from foreground blocking load.

State existence is insufficient. Human review determines whether copy,
placement, recovery, disclosure, and first-run semantics fit user intent.
Navigation checks should deterministically cover landmarks, current-page
state, keyboard reachability, bypass blocks, repeated-order consistency, and
focus restoration. Raw link count remains a heuristic: product depth and
grouping determine overload. WCAG requires consistent repeated navigation and
help, not one navigation topology. Sources: [Consistent Navigation](https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation.html),
[Consistent Help](https://www.w3.org/WAI/WCAG22/Understanding/consistent-help).

### Forms and errors

- Associate visible labels and descriptions using native elements first;
  placeholder text is not a persistent label. Source: [WAI Labeling Controls](https://www.w3.org/WAI/tutorials/forms/labels/).
- Validate `type`, `autocomplete`, `inputmode`, `required`, min/max/length,
  pattern, and field grouping against the mapped API contract. HTML treats
  field type, autofill purpose, and input modality as separate concerns.
  Source: [HTML forms guidance](https://html.spec.whatwg.org/multipage/forms.html#the-difference-between-the-field-type,-the-autofill-field-name,-and-the-input-modality).
- Preserve server-side validation. WAI explicitly notes that client-side
  validation alone is not security. Source: [WAI Validating Input](https://www.w3.org/WAI/tutorials/forms/validation/).
- Require error identification, correction guidance when known, association to
  fields, an accessible summary for multiple errors, preservation of user
  input, and focus placement that does not hide context.
- Test multi-step redundant entry and accessible authentication, including
  password-manager and copy/paste support. Sources: [Redundant Entry](https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry.html),
  [WCAG 2.2 Accessible Authentication](https://www.w3.org/TR/WCAG22/#accessible-authentication-minimum).

### Motion and visual presentation

Deterministic checks should cover user motion preferences, flash thresholds,
uncontrolled auto-updating content, focus loss, scroll/snap traps, and measured
main-thread/render cost. Animation style, spring choice, choreography,
delight, and brand fit remain review guidance. Never add motion solely to
satisfy a rule.

Typography checks should cover actual glyph fallback, language/script support,
font readiness, missing text, line overlap, text-spacing override, zoom/reflow,
line length as a review signal, and font-driven CLS/LCP. Typeface genre,
pairing, exact scale, and whether serif belongs in software are product/design
judgments.

### Performance and Core Web Vitals

- Add browser measurement for LCP, INP contributors, and CLS; retain raw
  entries, route/state/viewport, browser version, device class, and whether
  evidence is lab or field.
- Never claim a Core Web Vitals pass from one Playwright run. Thresholds apply
  to the 75th percentile of field page visits. Use CrUX or product RUM when
  available; synthetic evidence diagnoses, it does not replace field data.
  Sources: [Core Web Vitals workflows](https://web.dev/articles/vitals-tools),
  [field measurement](https://web.dev/articles/vitals-field-measurement-best-practices).
- Detect LCP resources hidden behind JavaScript/CSS discovery, lazy-loaded LCP
  candidates, missing intrinsic image dimensions, unreserved dynamic content,
  font shifts, and long interaction tasks. Sources: [Optimize LCP](https://web.dev/articles/optimize-lcp),
  [Optimize CLS](https://web.dev/articles/optimize-cls), [Optimize INP](https://web.dev/articles/optimize-inp).
- Treat universal selectors, DOM size, memoization, `will-change`, preload,
  passive listeners, and `content-visibility` as measured opportunities, not
  automatic defects. Performance advice without a trace or metric is a
  heuristic.
- Check back/forward navigation and lifecycle correctness where applicable;
  `unload` patterns, open connections, and stale restore behavior can block or
  corrupt bfcache use. Source: [web.dev bfcache guidance](https://web.dev/articles/bfcache).

### Internationalization and localization

- Require a valid default `lang` on HTML and language changes around foreign
  passages. Source: [W3C Declaring language in HTML](https://www.w3.org/International/questions/qa-html-language-declarations.html).
- Detect directionality intent and test RTL/mixed-direction content. Prefer
  flow-relative logical properties where layout should follow writing mode;
  physical positioning remains valid when intentionally physical. Sources:
  [W3C RTL markup guidance](https://www.w3.org/International/questions/qa-html-dir),
  [CSS Logical Properties](https://www.w3.org/TR/css-logical-1/).
- Exercise long translations, plural/select branches, different numeral/date
  formats, CJK line breaking, bidirectional isolation, emoji/grapheme clusters,
  IME composition, and Unicode/control characters.
- Do not hardcode one Latin-script line-height or letter-spacing threshold as a
  global typography violation. WCAG itself notes script-specific spacing
  exceptions.
- Locale quality, translation correctness, cultural tone, and whether content
  order remains meaningful require human review.

### Privacy and security

- Trace untrusted data to HTML, attribute, URL, JavaScript, CSS, and DOM sinks;
  apply context-specific encoding or sanitization. Prefer `textContent` and
  other safe sinks. Presence of a sanitizer import is not proof. Source:
  [OWASP XSS Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html).
- For `postMessage`, require an explicit expected target origin, exact sender
  origin validation, message-schema validation, and data-only handling. Source:
  [OWASP HTML5 Security](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html).
- Flag sensitive local/session storage, client-bundled secrets, unsafe URL
  protocols, open redirects, permissive iframe/cross-origin capabilities, and
  missing server security directives as evidence-backed risks.
- Map authorization at object/property/function level, not only “auth present.”
  Current OpenAPI extraction retains scheme names but not required scopes,
  header/cookie contracts, or property-level authorization evidence.
- Record purpose, collection, disclosure, retention, and user-control evidence
  for personal data. W3C privacy guidance prioritizes data minimization,
  purpose limitation, transparency, contextual permission prompts, and easy
  consent withdrawal. Source: [W3C Privacy Principles](https://www.w3.org/TR/privacy-principles/).
- Consent legitimacy, data necessity, dark patterns, legal basis, and policy
  accuracy require product/legal/human review; static source cannot prove them.

### Resilience and offline behavior

- Test timeout, abort, offline, DNS/network failure, 5xx, malformed response,
  partial data, stale cache, reconnect, duplicate submit, and process-resume
  scenarios when contract/topology evidence makes them applicable.
- Retry only when HTTP method/operation semantics permit it. RFC 9110 defines
  safe/idempotent semantics and warns against automatic retries of
  non-idempotent requests without additional knowledge.
- Honor `429` details and `Retry-After` when supplied. Source: [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html#section-4).
- Use `If-Match`/ETag preconditions where concurrent mutation can cause lost
  updates; surface `412`/conflict recovery without overwriting user work.
  Source: [RFC 9110 If-Match](https://www.rfc-editor.org/rfc/rfc9110.html#name-if-match).
- Service workers and Cache Storage can enable offline behavior, but are not a
  universal requirement. If present, test install/activate/fetch lifecycle,
  cache versioning, authenticated/private data, update races, and offline
  fallback. Source: [Service Workers](https://www.w3.org/TR/service-workers/).

### API, backend, and database contract lineage

Deepen the existing contract graph rather than adding a parallel schema:

- preserve OpenAPI version/dialect, servers, media types, parameters by
  location, headers, cookies, request bodies, response ranges/defaults,
  callbacks, webhooks, links, deprecation, and security requirements including
  scopes/roles;
- preserve JSON Schema composition, discriminator, read/write direction,
  defaults, formats, numeric/string/array bounds, nullability, unevaluated
  properties, and recursive/reference provenance;
- compare frontend request/response/error parsing with the exact selected
  media type and status, not only route/method and one schema;
- model a typed error family, preferably mapping compatible APIs to RFC 9457
  without requiring every API to adopt it;
- map pagination cursor/offset semantics, filters, sort stability, locale/time
  semantics, conditional requests, cache validators, rate limits, and mutation
  concurrency/retry behavior;
- retain backend handler -> service -> entity -> DB constraint lineage while
  respecting intentional DTO transformations and authorization filters;
- treat OpenAPI schemas as useful but not infallible. The OpenAPI project
  states that its schemas cannot catch every specification violation and that
  normative specification text wins. Source: [OpenAPI versions and schemas](https://spec.openapis.org/oas/).

Any artifact/schema extension needs external differential probes freezing
public signatures, exact errors, ordering, serialization, and old artifact
loading. Unknown, unsupported, ambiguous, stale, or contradictory evidence must
remain a blocker, not become a guessed mismatch.

### Observability and provenance

- Correlate mapped UI action/state -> HTTP client -> server route -> service ->
  DB operation with standard `traceparent`/`tracestate` propagation where the
  app already supports tracing.
- Use low-cardinality route templates and error classes; never substitute raw
  URL paths for route templates in metrics. Source: [OpenTelemetry HTTP metrics](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/).
- Capture DB system, namespace, collection, operation, status, duration, and a
  low-cardinality query summary. Do not collect non-parameterized query text by
  default without sanitization; query parameters are opt-in. Source:
  [OpenTelemetry database spans](https://opentelemetry.io/docs/specs/semconv/db/database-spans/).
- Allow server timing evidence to connect frontend latency with backend phases.
  Source: [W3C Server Timing](https://www.w3.org/TR/server-timing/).
- Redact secrets, credentials, personal data, query literals, and high-cardinality
  hostile values from logs/traces; bound every diagnostic and evidence section.
- Preserve entity/activity/agent/source derivation where useful without
  requiring full PROV-O serialization. Source: [W3C PROV-O](https://www.w3.org/TR/prov-o/).
- Keep intrinsic runtime observation status separate from frontend-map
  freshness. Provenance records what produced evidence; freshness records
  whether that evidence still corresponds to current source.

## Prioritized implementation matrix

| Priority | Owning seam | Smallest validated increment | Deterministic gate | Must remain review/evidence-gated |
|---|---|---|---|---|
| P0 | Analyzer rule catalog | Add evidence-class/applicability/source metadata using existing rule model; inventory every `WCAG`, security, and performance claim | Snapshot all 217 IDs, ordering, messages, and serialized issues before migration | Reclassification of taste severity |
| P0 | Analyzer facts/rules | Consolidate pure-black and purple-gradient duplicate fact extraction; demote taste-only compliance language | Differential probe proves same intentional matches and no duplicate issue for one source fact | Whether palette/font/layout is good for brand |
| P0 | Accessibility analyzer/runtime | 24px target+spacing exceptions, keyboard traversal, focus visibility/occlusion, actual state contrast, 320px reflow, spacing override | Hostile fixtures for inline/equivalent/UA/essential exceptions; desktop/mobile/zoom/forced-colors browser runs | Name quality, reading order meaning, assistive-tech usability |
| P0 | Forms + contract lineage | Label/description/error association, autocomplete/inputmode, client/server constraint parity, status-message evidence | Native HTML and framework fixtures; server/client mismatch RED tests; no hostile value echo | Validation timing, copy quality, cross-field remediation |
| P0 | Security analyzer | Replace sanitizer-token bypass with source-to-sink proof; exact `postMessage` origin plus message-shape checks | Known-safe/unsafe sink corpus; aliases, wrappers, post-sanitize mutation, Unicode/URL payloads | Threat model, business authorization, consent legitimacy |
| P0 | Full-stack guidance/assets | Correct 401/403, DB leakage, shared-type, env-secret, URL, and timestamp guidance; preserve root/bundle parity | Exact `cmp` root/bundle assets and wheel resource verification | Product recovery paths |
| P1 | Runtime observer/findings | Add LCP/CLS lab evidence and INP contributor capture; label lab versus field | Deterministic fixture with reserved/unreserved media and long interaction task; bounded artifacts | Core Web Vitals field pass and user-perceived speed |
| P1 | Experience-state planner | Extend canonical state coverage only from proven transport/auth/concurrency evidence | External serialization probe; owner with read+mutation; unknown evidence fails closed | Which states merit dedicated UI versus inline status |
| P1 | Contract adapters/graph | Preserve media types, parameter locations, headers/cookies, security scopes, default/ranged responses, deprecation, callbacks/webhooks/links | OpenAPI 3.0/3.1/3.2 fixtures; JSON Schema composition; stable old artifact load | Intentional transformation and authorization correctness |
| P1 | Remediation planner/prototype | Generate source-aware retry/rate-limit/conflict/offline/auth remediation from proven contracts | `429`/`Retry-After`, `401`, `403`, `412`, timeout, abort, duplicate-submit fixtures; resource ceilings | Copy, disclosure, optimistic interaction appropriateness |
| P1 | i18n runtime scenarios | Add RTL, long translation, CJK, bidi, grapheme, locale/date, IME, and text-spacing scenarios | Stable multilingual fixtures across widths and zoom; logical/physical property evidence | Translation and cultural quality |
| P1 | Observability lineage | Optional trace/Server-Timing/DB evidence adapter using existing lineage nodes | Bounded/redacted low-cardinality smoke; malformed headers; no raw query values | Whether app should adopt instrumentation |
| P2 | Navigation/content review | Replace raw-count verdict with grouped landmark/topology evidence and explicit heuristic confidence | Stable sampling/order, keyboard reachability, current location, consistent repeated order | Cognitive load, label clarity, information scent |
| P2 | Resilience/offline | Browser scenarios for offline/reconnect/bfcache/service-worker behavior when capabilities exist | No-op, resume, stale cache, update race, aborted request, private-cache fixtures | Whether offline support is product-required |
| P2 | Taste references | Remove universal font/color/motion/layout mandates; retain anti-slop options tied to intent/dials | Root/bundle parity; reference-link integrity | All aesthetic recommendations |

## Acceptance policy

A new deterministic rule is ready only when:

1. an owning primary source or measured local invariant is cited;
2. applicability and every material exception are encoded or the result is
   explicitly heuristic;
3. RED tests include valid counterexamples, not only obvious failures;
4. runtime rules use real computed behavior rather than syntax as a proxy;
5. source ownership and contract lineage remain attached when proven;
6. unknown/ambiguous/stale/contradictory evidence fails closed;
7. hostile values cannot escape evidence boundaries or diagnostic budgets;
8. public signatures, exact errors, serialization, and order are frozen before
   schema/module refactors;
9. root and bundled assets remain byte-identical; and
10. automated output says what it proved, never “accessible,” “secure,”
    “performant,” or “contract-correct” from partial evidence.

## Recommended implementation order

1. Reclassify and correct current rule claims without adding rule count.
2. Consolidate duplicate source-fact extraction and preserve rule-ID migration
   evidence before removing any public finding.
3. Implement WCAG 2.2 AA target/focus/reflow/forms seams one RED/GREEN slice at
   a time.
4. Deepen OpenAPI/HTTP error, auth, concurrency, and resilience lineage.
5. Add lab performance, i18n, privacy, and observability evidence adapters.
6. Expand human review prompts only after deterministic evidence identifies the
   exact route, state, viewport, owner, and contract involved.

This order raises correctness before breadth. Adding more unclassified regex
rules would increase false confidence and remediation churn without improving
UI/UX outcomes.
