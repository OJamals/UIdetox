# Runtime scenario observation

UIdetox uses one browser observer for mapping and screenshot capture. A normal
`uidetox map --runtime` call is the default scenario: navigate, wait for bounded
request idle, apply the configured settle fallback, then capture `initial`.

Projects may set `runtime_scenarios` in `.uidetox/config.json` to a JSON file
inside the project root. Each scenario declares an absolute local URL, optional
viewport names from the shared registry, a readiness policy, ordered actions,
and capture states:

```json
[
  {
    "name": "empty-search",
    "url": "http://localhost:3000/search",
    "expected_state": "empty",
    "readiness": {"selector": "[data-app-ready=true]", "request_idle_ms": 0},
    "actions": [
      {"kind": "fill", "selector": "#query", "env": "UIDETOX_SEARCH_QUERY"},
      {"kind": "key", "selector": "#query", "key": "Enter"},
      {"kind": "wait-for-selector", "selector": "[data-state=empty]"},
      {"kind": "capture", "state": "empty"}
    ]
  }
]
```

Supported actions are `click`, `fill`, `key`, `wait-for-selector`,
`wait-for-state`, and `capture`. Timeouts are bounded at 30 seconds. Every fill
value must use an uppercase `env` reference; inline values are rejected
regardless of selector spelling. Each action accepts only its own fields.
Selector waits accept `attached`, `detached`, `visible`, or `hidden`; page waits
accept `load`, `domcontentloaded`, or `networkidle`. Scenario files never
contain credentials. UIdetox does not infer credentials, crawl controls, or
click destructive actions.

Readiness prefers an explicit selector or app hook. Mutation idle and bounded
request idle are available when the app has no explicit signal. Request-idle
timeout followed by settle is recorded as `degraded`; a missing explicit signal
fails the capture. Browser console, page, HTTP, request, and action failures
become canonical typed findings and retain scenario, state, URL, viewport,
capture, and source provenance. Repeated capture snapshots project one queue
candidate per distinct diagnostic.

Observation status is derived from the requested capture matrix:

- `current`: every capture completed with qualified readiness and coverage.
- `degraded`: every capture completed, but readiness fell back or DOM coverage
  was truncated.
- `partial`: some requested captures completed and some failed.
- `failed`: no requested capture completed.
- `absent`: no runtime capture was requested.

Only `current` evidence is trusted as current runtime evidence. Source changes
turn retained evidence `stale`; partial or failed evidence never becomes
current because a page happened to render.

DOM traversal has explicit scan and candidate budgets. Interactive,
source-anchored, structural, clipped, and scrolling elements receive priority.
Every capture records total, candidate, eligible, emitted, budget, and
truncation counts. Geometry, styles, scroll axes, descendant bounds, and
clipping ancestry share one per-element cache. Logical axes cover horizontal,
vertical, sideways, LTR, and RTL writing modes. Peer groups are analyzed once
per flex/grid parent without a sibling cap.

The shared viewport registry remains the baseline for map and capture. Runtime
mapping also discovers pixel-valued media and container-query boundaries from
the shared frontend file set, then adds bounded probes one pixel below and
above each selected boundary. The artifact records boundary kinds, source
files, the total discovered count, and whether selection was truncated.
