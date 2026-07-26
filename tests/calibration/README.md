# Calibration corpus

`manifest.json` is the versioned source of truth for deterministic capability
qualification. Each case points to a local fixture and classifies expected
behavior as `positive`, `negative`, `degraded`, or `unsupported`.

Static analyzer cases run against the live rule registry. Degraded and
unsupported cases document known gaps owned by plans 015–019; they are reported
separately and never included in objective precision or recall.

Fixtures are intentionally minimal source trees. Do not add downloaded
applications or another runner outside pytest.

Contract-lineage cases assert exact causal finding sets across shape parity
with unknown evidence, field type, enum, requiredness, authentication, and
incomplete response evidence. Same-route source observations remain distinct;
the expected finding set is deduplicated by cause, not by route.
