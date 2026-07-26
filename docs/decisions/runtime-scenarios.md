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
      {"kind": "fill", "selector": "#query", "value": "no-match"},
      {"kind": "key", "selector": "#query", "key": "Enter"},
      {"kind": "wait-for-selector", "selector": "[data-state=empty]"},
      {"kind": "capture", "state": "empty"}
    ]
  }
]
```

Supported actions are `click`, `fill`, `key`, `wait-for-selector`,
`wait-for-state`, and `capture`. Timeouts are bounded at 30 seconds. Sensitive
fills must use an uppercase `env` reference; scenario files never contain
credentials. UIdetox does not infer credentials, crawl controls, or click
destructive actions.

Readiness prefers an explicit selector or app hook. Mutation idle and bounded
request idle are available when the app has no explicit signal. Request-idle
timeout followed by settle is recorded as `degraded`; a missing explicit signal
fails the capture. Browser console, page, HTTP, request, and action failures
retain scenario, state, URL, viewport, and source provenance.

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
vertical, sideways, LTR, and RTL writing modes.
