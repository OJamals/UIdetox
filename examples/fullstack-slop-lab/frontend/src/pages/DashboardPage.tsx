import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ActivityFeed } from "../components/ActivityFeed";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type { Activity, Metrics } from "../types";

const monthlyThroughput = [
  ["Jan", 38], ["Feb", 62], ["Mar", 45], ["Apr", 78], ["May", 58], ["Jun", 88],
] as const;

export function DashboardPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [recommendations, setRecommendations] = useState<Array<{ title: string; score: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.getMetrics(), api.getActivity(), api.getRecommendations()])
      .then(([nextMetrics, nextActivity, nextRecommendations]) => {
        setMetrics(nextMetrics);
        setActivity(nextActivity);
        setRecommendations(nextRecommendations);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Workspace summary could not be loaded."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner label="Loading workspace summary…" />;

  return (
    <div className="page dashboard-page">
      <header className="page-heading dashboard-heading">
        <div>
          <span className="eyebrow">Operations ledger / current snapshot</span>
          <h1>Northstar workspace</h1>
          <p>Delivery state, recent changes, and model recommendations from the fixture API.</p>
        </div>
        <Link className="primary-button" to="/projects">Open project register</Link>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <section className="portfolio-ledger" aria-labelledby="portfolio-summary-title">
        <div className="primary-measure">
          <span className="eyebrow">Average completion</span>
          <h2 id="portfolio-summary-title">{metrics?.averageProgress ?? 0}%</h2>
          <p>Across {metrics?.activeProjects ?? 0} active projects.</p>
        </div>
        <dl className="measure-ledger">
          <div><dt>Completed projects</dt><dd>{metrics?.completedProjects ?? 0}</dd></div>
          <div><dt>Team velocity</dt><dd>{metrics?.teamVelocity ?? 0}%</dd></div>
          <div><dt>Customer health</dt><dd>{metrics?.customerHappiness ?? 0}%</dd></div>
        </dl>
      </section>

      <div className="dashboard-grid">
        <OperationalSection eyebrow="01 / Throughput" title="Six-month delivery signal">
          <div className="fake-chart" aria-label="Monthly delivery throughput">
            {monthlyThroughput.map(([month, height]) => (
              <div className="fake-chart-column" key={month}>
                <span className="fake-chart-value">{height}</span>
                <span className="fake-chart-bar" style={{ height }} />
                <small>{month}</small>
              </div>
            ))}
          </div>
        </OperationalSection>

        <OperationalSection eyebrow="02 / Activity" title="Recent workspace changes">
          <ActivityFeed items={activity} />
        </OperationalSection>
      </div>

      <section className="recommendation-ledger" aria-labelledby="recommendations-title">
        <header><span className="eyebrow">03 / Recommendations</span><h2 id="recommendations-title">Review queue</h2></header>
        {recommendations.length ? (
          <ol>
            {recommendations.map((item) => (
              <li key={item.title}><span>{item.title}</span><b>{item.score}% confidence</b></li>
            ))}
          </ol>
        ) : <p>No recommendations are currently available.</p>}
      </section>
    </div>
  );
}
