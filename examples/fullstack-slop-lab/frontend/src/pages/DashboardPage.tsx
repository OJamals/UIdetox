import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ActivityFeed } from "../components/ActivityFeed";
import { MagicCard } from "../components/MagicCard";
import { MetricCard } from "../components/MetricCard";
import { Spinner } from "../components/Spinner";
import type { Activity, Metrics } from "../types";

export function DashboardPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [recommendations, setRecommendations] = useState<
    Array<{ title: string; score: number }>
  >([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.getMetrics(), api.getActivity()])
      .then(([nextMetrics, nextActivity]) => {
        setMetrics(nextMetrics);
        setActivity(nextActivity);
      })
      .catch((reason) => {
        console.log(reason);
        setError("Oops! Something went wrong...");
      })
      .finally(() => setLoading(false));

    api
      .getRecommendations()
      .then(setRecommendations)
      .catch(() => setRecommendations([]));
  }, []);

  if (loading) return <Spinner label="Generating magical insights..." />;

  return (
    <div className="page dashboard-page">
      <section className="hero-gradient glass-card">
        <div className="aurora one" />
        <div className="aurora two" />
        <span className="sparkle-badge">✨ AI-POWERED WORKSPACE</span>
        <h1>
          Supercharge your <em>workflow</em>
        </h1>
        <p>
          Unleash the power of next-generation collaboration and transform the way your
          modern team works.
        </p>
        <div className="hero-actions">
          <button className="primary-button">Get started for free</button>
          <button className="secondary-button">Watch demo ▶</button>
        </div>
      </section>

      {error && <div className="error-banner">{error}</div>}

      <div className="metrics-grid">
        <MetricCard
          icon="🚀"
          label="Active projects"
          value={String(metrics?.activeProjects ?? 0)}
          trend="+24% this month"
        />
        <MetricCard
          icon="✅"
          label="Completed"
          value={String(metrics?.completedProjects ?? 0)}
          trend="+18% this month"
          tone="blue"
        />
        <MetricCard
          icon="⚡"
          label="Team velocity"
          value={`${metrics?.teamVelocity ?? 0}%`}
          trend="+12% this week"
          tone="pink"
        />
        <MetricCard
          icon="😍"
          label="Happiness"
          value={`${metrics?.customerHappiness ?? 0}%`}
          trend="Best ever!"
          tone="orange"
        />
      </div>

      <div className="dashboard-grid">
        <MagicCard
          className="chart-card"
          eyebrow="01 / PERFORMANCE"
          title="Your amazing growth"
          action={<button className="pill-button">Last 30 days⌄</button>}
        >
          <div className="fake-chart">
            {[38, 62, 45, 78, 58, 88, 72, 97, 84, 110, 92, 126].map(
              (height, index) => (
                <span key={index} style={{ height }} />
              ),
            )}
          </div>
          <div className="chart-labels">
            <span>Jan</span>
            <span>Feb</span>
            <span>Mar</span>
            <span>Apr</span>
            <span>May</span>
            <span>Jun</span>
          </div>
        </MagicCard>

        <MagicCard eyebrow="02 / PROGRESS" title="Overall completion">
          <div className="progress-ring">
            <div>
              <strong>{metrics?.averageProgress ?? 0}%</strong>
              <small>Complete</small>
            </div>
          </div>
          <div className="mini-stats">
            <span>
              <i className="dot purple" /> In progress <b>8</b>
            </span>
            <span>
              <i className="dot blue" /> In review <b>3</b>
            </span>
            <span>
              <i className="dot pink" /> Blocked <b>2</b>
            </span>
          </div>
        </MagicCard>

        <MagicCard
          className="activity-card"
          eyebrow="03 / ACTIVITY"
          title="What's happening"
          action={<button className="text-link">View all →</button>}
        >
          <ActivityFeed items={activity} />
        </MagicCard>

        <MagicCard eyebrow="04 / AI MAGIC" title="Smart recommendations">
          {recommendations.length ? (
            recommendations.map((item) => (
              <div className="recommendation" key={item.title}>
                <span>✨</span>
                <div>
                  <b>{item.title}</b>
                  <small>{item.score}% confidence</small>
                </div>
              </div>
            ))
          ) : (
            <div className="empty-magic">
              <span>🪄</span>
              <p>No insights yet</p>
              <button>Generate now</button>
            </div>
          )}
        </MagicCard>
      </div>
    </div>
  );
}

