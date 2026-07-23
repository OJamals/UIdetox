import intent from "../../../fixture-intent.json";

const evidence = [
  ["Baseline analyzer findings", intent.remediation_evidence.baseline_static_issues],
  ["Baseline frontend-only operations", intent.remediation_evidence.baseline_operation_parity.frontend_only],
  ["Baseline backend-only operations", intent.remediation_evidence.baseline_operation_parity.backend_only],
  ["Target parity findings", Object.values(intent.remediation_evidence.target_operation_parity).reduce((sum, value) => sum + value, 0)],
] as const;

export function FixtureProvenancePage() {
  return (
    <div className="fixture-page provenance-page">
      <header className="provenance-hero">
        <span className="eyebrow">Synthetic fixture / remediation evidence</span>
        <h1>Why this interface exists</h1>
        <p>{intent.product_goal}</p>
        <div className="provenance-seal"><b>0</b><span>production customer records</span><small>Guaranteed by the canonical manifest</small></div>
      </header>

      <section className="provenance-ledger" aria-labelledby="intent-title">
        <header><span className="eyebrow">Canonical direction</span><h2 id="intent-title">Intent and design contract</h2></header>
        <dl><div><dt>Audience</dt><dd>{intent.audience}</dd></div><div><dt>Primary job</dt><dd>{intent.primary_job}</dd></div><div><dt>Tone</dt><dd>{intent.tone}</dd></div><div><dt>Genre</dt><dd>{intent.genre}</dd></div></dl>
      </section>

      <section className="portfolio-ledger" aria-labelledby="evidence-title">
        <div className="primary-measure"><span className="eyebrow">Qualification lineage</span><h2 id="evidence-title">Before → after</h2><p>Baseline defects remain recorded even after their root causes are corrected.</p></div>
        <dl className="measure-ledger">{evidence.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      </section>

      <div className="provenance-columns">
        <section><h2>Preserve contract</h2><ul>{intent.preserve.map((item) => <li key={item}>{item}</li>)}</ul></section>
        <section><h2>Fixture constraints</h2><ul>{intent.constraints.map((item) => <li key={item}>{item}</li>)}</ul></section>
        <section><h2>Lineage</h2><ol>{intent.provenance.lineage.map((source) => <li key={source}>{source}</li>)}</ol></section>
      </div>

      <section className="provenance-route-wall"><h2>Preserved route surface</h2><div>{intent.expected_frontend_routes.map((route, index) => <span key={route}><b>{String(index + 1).padStart(2, "0")}</b>{route}</span>)}</div></section>
      <p className="provenance-footnote">Source-of-truth chain: {intent.provenance.sources_of_truth.join(" → ")}. Remediated {intent.provenance.remediated_on}.</p>
    </div>
  );
}
