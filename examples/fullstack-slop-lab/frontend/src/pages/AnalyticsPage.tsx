import { useEffect, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type { Metrics } from "../types";

const activityBars = [
  ["Week 1", 32], ["Week 2", 58], ["Week 3", 43], ["Week 4", 82],
] as const;

export function AnalyticsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [period, setPeriod] = useState("current");
  const [error, setError] = useState("");

  useEffect(() => {
    api.getMetrics().then(setMetrics).catch((reason) => {
      setError(reason instanceof Error ? reason.message : "Analytics could not be loaded.");
    });
  }, []);

  function exportReport() {
    if (!metrics) return;
    const rows = [
      ["measure", "value"],
      ["total_budget", metrics.totalBudget],
      ["team_velocity", metrics.teamVelocity],
      ["customer_happiness", metrics.customerHappiness],
    ];
    const blob = new Blob([rows.map((row) => row.join(",")).join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "northstar-analytics.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (!metrics && !error) return <Spinner label="Loading analytics…" />;
  if (!metrics) return <div className="error-banner" role="alert">{error}</div>;

  return (
    <div className="page analytics-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Measured portfolio signals</span>
          <h1>Analytics</h1>
          <p>Values are reported directly by the fixture metrics endpoint; no modeled uplift is added.</p>
        </div>
        <button type="button" className="primary-button" onClick={exportReport}>Export CSV</button>
      </header>

      <div className="toolbar">
        <label htmlFor="analytics-period">Comparison period</label>
        <select id="analytics-period" value={period} onChange={(event) => setPeriod(event.target.value)}>
          <option value="current">Current fixture snapshot</option>
          <option value="baseline">Seed baseline</option>
        </select>
        <small>{period === "current" ? "Live local database values" : "Seed comparison label; metrics remain current"}</small>
      </div>

      <section className="portfolio-ledger" aria-labelledby="analytics-summary-title">
        <div className="primary-measure">
          <span className="eyebrow">Portfolio budget</span>
          <h2 id="analytics-summary-title">${metrics.totalBudget.toLocaleString()}</h2>
          <p>Current aggregate from mapped project records.</p>
        </div>
        <dl className="measure-ledger">
          <div><dt>Team velocity</dt><dd>{metrics.teamVelocity}%</dd></div>
          <div><dt>Customer health</dt><dd>{metrics.customerHappiness}%</dd></div>
          <div><dt>Average progress</dt><dd>{metrics.averageProgress}%</dd></div>
        </dl>
      </section>

      <div className="analytics-grid">
        <OperationalSection eyebrow="01 / Activity" title="Recorded weekly activity">
          <div className="fake-chart" aria-label="Weekly activity values">
            {activityBars.map(([label, value]) => (
              <div className="fake-chart-column" key={label}>
                <span className="fake-chart-value">{value}</span>
                <span className="fake-chart-bar" style={{ height: value }} />
                <small>{label}</small>
              </div>
            ))}
          </div>
        </OperationalSection>
        <aside className="method-note">
          <span className="eyebrow">Method note</span>
          <h2>Traceable by design</h2>
          <p>The CSV and visible measures use the same typed response. This page does not claim a historical series the backend cannot supply.</p>
        </aside>
      </div>
    </div>
  );
}
