import { useEffect, useState } from "react";
import { api } from "../api/client";
import { MagicCard } from "../components/MagicCard";
import { MetricCard } from "../components/MetricCard";
import { Spinner } from "../components/Spinner";
import type { Metrics } from "../types";

const bars = [32, 58, 43, 82, 67, 95, 74, 111, 89, 122, 103, 138];

export function AnalyticsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  useEffect(() => {
    api.getMetrics().then(setMetrics);
  }, []);

  if (!metrics) return <Spinner label="Analyzing your success..." />;

  return (
    <div className="page">
      <div className="page-heading centered">
        <div>
          <span className="sparkle-badge">✨ POWERFUL ANALYTICS</span>
          <h1 className="gradient-text">Insights that inspire action</h1>
          <p>Transform raw data into magical decisions that supercharge growth.</p>
        </div>
        <button className="primary-button">Export beautiful report</button>
      </div>

      <div className="metrics-grid three">
        <MetricCard
          icon="💰"
          label="Total portfolio value"
          value={`$${Math.round(metrics.totalBudget / 1000)}K`}
          trend="+47% vs last year"
        />
        <MetricCard
          icon="⚡"
          label="Average velocity"
          value={`${metrics.teamVelocity}%`}
          trend="10x faster"
          tone="blue"
        />
        <MetricCard
          icon="🎯"
          label="Success rate"
          value="99.9%"
          trend="Industry leading"
          tone="pink"
        />
      </div>

      <div className="analytics-grid">
        <MagicCard
          className="wide-card"
          eyebrow="01 / REVENUE"
          title="Exponential growth"
          action={<button className="pill-button">This year⌄</button>}
        >
          <div className="area-chart">
            <div className="grid-lines" />
            <div className="mountain-chart" />
          </div>
        </MagicCard>

        <MagicCard eyebrow="02 / CHANNELS" title="Top performers">
          {[
            ["Organic", 84, "#7c3aed"],
            ["Social", 67, "#2563eb"],
            ["Referral", 53, "#ec4899"],
            ["Direct", 41, "#f59e0b"],
          ].map(([name, value, color]) => (
            <div className="channel-row" key={String(name)}>
              <span>{name}</span>
              <div>
                <i style={{ width: `${value}%`, background: color }} />
              </div>
              <b>{value}%</b>
            </div>
          ))}
        </MagicCard>

        <MagicCard className="wide-card" eyebrow="03 / ENGAGEMENT" title="Activity overview">
          <div className="bar-chart">
            {bars.map((height, index) => (
              <span key={index} style={{ height }} />
            ))}
          </div>
        </MagicCard>

        <MagicCard eyebrow="04 / SENTIMENT" title="Customer love">
          <div className="emoji-score">😍</div>
          <strong className="huge-score">{metrics.customerHappiness}%</strong>
          <p>Customers absolutely love the experience!</p>
          <button className="text-link">See all feedback →</button>
        </MagicCard>
      </div>
    </div>
  );
}

