# Capability qualification

UIdetox uses pytest as its only qualification runner. Install contributor and
audit dependencies from a clean checkout:

```bash
python -m pip install --upgrade "pip>=26.1.2"
python -m pip install -e '.[dev]'
```

## Gates

Run the complete deterministic suite:

```bash
python -m pytest -q -W error
```

Run the versioned cross-framework calibration matrix alone:

```bash
python -m pytest -q -W error tests/test_calibration_matrix.py
```

The matrix reports true positives, false positives, false negatives, degraded
cases, and unsupported cases by capability and framework. Unpaired rules stay
explicitly manual; adding or changing a catalog rule invalidates the manifest
contract until its classification is reviewed.

Run live localhost-only Playwright qualification:

```bash
python -m pytest -q -W error -m browser
```

Install browser support first with:

```bash
python -m pip install -e '.[dev,capture]'
python -m playwright install chromium
```

Browser tests may skip only when Chromium is absent and must include that reason.
They use the checked-in full-stack lab, all supported viewports, deterministic
structured evidence, screenshots, readiness checks, and a shared server fixture
that proves subprocess cleanup.

Run installed-wheel smoke and canonical asset parity:

```bash
python -m pytest -q -W error tests/test_release_readiness.py tests/test_update_skill.py
```

This gate builds one wheel, checks bundled skill/command/reference/provider
assets against canonical sources, installs the wheel, and runs its CLI outside
the checkout. Release CI runs the same suite on Python 3.11–3.13 across Ubuntu
and Windows before building the upload artifact once.

Audit the active environment:

```bash
python -m pip_audit --strict --desc
```

Do not blanket-ignore advisories. A temporary exception must name the package,
advisory, rationale, expiry date, and tracking issue. An advisory reachable from
production code blocks release and requires its own remediation plan.
