# Full-Stack UI Integration

## Contract Lineage

Map every visible read, mutation, state, and recovery action through:

UI owner → client call → HTTP/async operation → backend handler → service policy → database/schema

Preserve source anchors, provenance, confidence, and freshness at every edge. Frontend wire types must match authoritative contract. View models may differ only through an explicit, tested transformation. Never create a second hand-maintained schema to patch a mismatch.

For OpenAPI, preserve version/dialect, servers, media types, parameter locations, headers/cookies, security schemes and required scopes, response ranges/defaults, deprecation, callbacks/webhooks/links, nullability, composition/discriminators, and read/write direction. Use [OpenAPI published specifications](https://spec.openapis.org/oas/) and [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) as contract sources where applicable.

## Authority and Validation

Client validation improves feedback; server remains authoritative for validation, authorization, state transitions, prices, permissions, and database invariants.

- Mirror required fields, ranges, lengths, enum values, formats, nullability, and cross-field rules when contract evidence exists.
- Treat client controls and hidden UI as usability, never authorization.
- Map server validation pointers to owning field; retain a safe form-level summary for unmapped or global problems.
- Do not expose internal schema names, stack traces, SQL, secrets, or policy internals in user-facing errors.
- Test stale clients and independently deployed frontend/backend versions.

Use [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) for verification scope; authorization and trusted validation belong on trusted service layer.

## Errors and HTTP Semantics

Prefer stable machine-readable error identity. [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html) problem details provide a standard application/problem+json shape when API needs one.

- Branch on status, problem type, or documented extension codes—not localized title or detail.
- Keep actual HTTP status consistent with any problem status.
- Use safe, actionable occurrence detail and a correlation/instance reference when useful.
- Preserve field pointers for validation errors.
- Honor Retry-After where supplied.
- Treat 401 as missing/invalid authentication and start session recovery or reauthentication when appropriate.
- Treat 403 as understood but forbidden; preserve context and offer only allowed recovery.
- Model 404, 409, 410, 412, 422, 429 rate limit, timeout, abort, offline, malformed response, and 5xx distinctly when contracts expose them.

## Mutations, Concurrency, and Retry

- Disable duplicate submission while an identical mutation is in flight, but keep cancellation/recovery accessible.
- Retry automatically only when operation semantics and idempotency evidence make it safe. Add bounded exponential backoff with jitter where appropriate.
- Use idempotency keys only when server defines their scope, retention, replay, and response behavior.
- For optimistic updates, preserve prior state and rollback or reconcile after failure. Avoid optimistic success for payments, irreversible actions, security-sensitive changes, or unresolved conflicts.
- Preserve concurrency tokens such as ETags/version fields. Map failed preconditions or version conflicts to reload, compare, merge, overwrite, or cancel paths supported by policy.
- Distinguish atomic failure from partial success. Batch UI must show item-level outcomes and safe retry scope when API permits partial completion.
- After mutation, perform evidence-backed cache invalidation or updates for every affected read owner without erasing fresher server data.
- In React effects, include every reactive value from component scope, but do not demand module-scope constants as dependencies. Parse each effect boundary independently; never infer missing dependencies by spanning into another component or effect. Mirror setup with cleanup for subscriptions and other external systems.

Reference: [HTTP Semantics, RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html).

## State Coverage

Each operation owner must cover applicable states, not one universal list:

- initial and first-run;
- loading, delayed, progress, and retrying;
- empty and filtered-zero-results;
- ready/success;
- disabled with reason or recovery;
- validation, authentication, forbidden, not-found, conflict, rate-limited, and server errors;
- cancelled and aborted;
- offline and reconnecting;
- stale, cached, partial, and background-refresh data;
- optimistic pending, rolled back, and reconciled.

Keep intrinsic runtime capture status separate from frontend-map freshness. Announce meaningful asynchronous status without stealing focus.

## Pagination, Streaming, and Realtime

- Preserve cursor/offset semantics, sort/filter coupling, total-count confidence, page-size limits, and stable identity.
- Cancel or ignore superseded reads. Prevent slower stale responses from replacing newer intent.
- For streams or subscriptions, define ordering, deduplication, resume cursor, reconnect backoff, heartbeat/timeout, and terminal error behavior.
- Keep virtualized content keyboard-reachable and expose position/count semantics where users need them.
- Do not claim complete search or list results when data is truncated, sampled, stale, or partially loaded.

## Resilience and Offline

Offline behavior is a product capability, not an automatic service-worker requirement.

- Distinguish offline, DNS/network failure, timeout, abort, server failure, and captive/blocked requests.
- Preserve unsent user input across recoverable failures.
- Define cache versioning, private/authenticated data rules, eviction, update races, and stale disclosure before enabling offline writes.
- Test reconnect, back/forward cache restoration, tab suspension, duplicated delivery, and no-op resume.
- Do not offer retry when it can duplicate a non-idempotent effect.

## Performance Contract

Measure field behavior at 75th percentile, segmented by route/device where data is sufficient. Current Core Web Vitals are LCP, INP, and CLS; good thresholds are LCP ≤2.5s, INP ≤200ms, and CLS ≤0.1. Lab tools diagnose; field data validates user experience.

- Tie LCP resources to source ownership and priority.
- Reserve dimensions for images, embeds, async content, and font fallback to control CLS.
- Keep long tasks and interaction work within an explicit response budget; avoid hiding latency behind motion.
- Treat performance changes as UX changes: preserve accessibility, correctness, and visual intent.

Reference: [Core Web Vitals thresholds](https://web.dev/articles/defining-core-web-vitals-thresholds).

## Security, Privacy, and Observability

- Never bundle secrets, privileged credentials, or authorization policy into client code.
- Trace untrusted data to exact sink. Sanitizer-library presence alone is not proof of safe use.
- Validate postMessage origin and message shape; constrain redirects and URL sinks.
- Minimize telemetry. Do not log tokens, secrets, raw form data, unnecessary personal data, or hostile artifact contents.
- Correlate user-safe error references with backend request/trace IDs.
- Preserve trace context across services and record route/operation identity, latency, outcome, retry, cache, and DB evidence without high-cardinality sensitive labels.
- Use Server-Timing or equivalent only for intentionally disclosed diagnostics.
- Keep debug logging distinct from production structured observability.

References: [W3C Trace Context](https://www.w3.org/TR/trace-context/) and [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/).

## Acceptance

Source-aware remediation is complete only when:

- UI state and copy map to exact API/backend/DB behavior;
- validation, authorization, errors, retries, conflicts, caching, and mutation consequences have source evidence;
- accessibility and responsive behavior survive real-browser desktop/mobile plus keyboard and preference checks;
- no-op runs preserve exact artifacts/captures;
- changed runs retain before/after provenance;
- untrusted evidence stays bounded and isolated;
- public signatures, errors, serialization, ordering, and freshness semantics remain stable unless an intentional contract change is proven.
