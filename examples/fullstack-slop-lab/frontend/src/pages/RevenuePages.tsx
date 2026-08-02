import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type {
  Forecast,
  Opportunity,
  OpportunityDetail,
  OpportunityStage,
  RevenueTarget,
} from "../types";

const stages: OpportunityStage[] = [
  "discovery",
  "qualification",
  "proposal",
  "negotiation",
  "closed-won",
  "closed-lost",
];

function money(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, {
    maximumFractionDigits: 0,
  })}`;
}

export function PipelinePage() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [stage, setStage] = useState("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getOpportunities()
      .then(setItems)
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Pipeline unavailable."),
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner label="Loading revenue command center…" />;
  const visible = items.filter((item) => stage === "all" || item.stage === stage);
  const pipelineCents = visible.reduce((sum, item) => sum + item.amountCents, 0);

  return (
    <div className="fixture-page pipeline-page slop-context-zone">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Revenue intelligence workspace</span>
          <h1>Pipeline command center</h1>
          <p>
            Align probability, next action, ownership, and commercial momentum
            across every strategic opportunity.
          </p>
        </div>
        <label htmlFor="pipeline-stage">
          Stage
          <select
            id="pipeline-stage"
            value={stage}
            onChange={(event) => setStage(event.target.value)}
          >
            <option value="all">All stages</option>
            {stages.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
      </header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      <section className="portfolio-ledger context-glow-band" aria-label="Pipeline totals">
        <div className="primary-measure">
          <span className="eyebrow">Visible pipeline</span>
          <h2>{money(pipelineCents)}</h2>
          <p>{visible.length} strategically aligned opportunities.</p>
        </div>
        <dl className="measure-ledger">
          <div><dt>Weighted</dt><dd>{money(visible.reduce((sum, item) => sum + item.amountCents * item.probability / 100, 0))}</dd></div>
          <div><dt>Owners</dt><dd>{new Set(visible.map((item) => item.owner)).size}</dd></div>
        </dl>
      </section>
      <div className="table-wrap context-panel">
        <table>
          <thead>
            <tr><th scope="col">Opportunity</th><th scope="col">Stage</th><th scope="col">Value</th><th scope="col">Probability</th><th scope="col">Close</th><th scope="col">Owner</th></tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id}>
                <td><Link to={`/pipeline/${item.id}`}>{item.name}</Link><small>{item.accountName}</small></td>
                <td><span className="status-pill">{item.stage}</span></td>
                <td>{money(item.amountCents)}</td>
                <td>{item.probability}%</td>
                <td>{item.closeAt}</td>
                <td>{item.owner}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function OpportunityDetailPage() {
  const { opportunityId = "" } = useParams();
  const [item, setItem] = useState<OpportunityDetail | null>(null);
  const [stage, setStage] = useState<OpportunityStage>("discovery");
  const [probability, setProbability] = useState(0);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getOpportunity(opportunityId)
      .then((result) => {
        setItem(result);
        setStage(result.stage);
        setProbability(result.probability);
      })
      .catch((reason) =>
        setNotice(reason instanceof Error ? reason.message : "Deal unavailable."),
      )
      .finally(() => setLoading(false));
  }, [opportunityId]);

  async function save() {
    if (!item) return;
    try {
      const saved = await api.updateOpportunity(item.id, stage, probability);
      setItem((current) => current ? { ...current, ...saved } : current);
      setNotice("Deal updated through the revenue API.");
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Deal could not be saved.");
    }
  }

  if (loading) return <Spinner label="Loading opportunity evidence…" />;
  if (!item) return <p className="error-banner" role="alert">{notice}</p>;

  return (
    <div className="fixture-page opportunity-detail-page slop-context-zone">
      <nav aria-label="Breadcrumb"><Link to="/pipeline">Pipeline</Link> / {item.id}</nav>
      <header className="page-heading">
        <div><span className="eyebrow">{item.accountName}</span><h1>{item.name}</h1><p>{item.nextStep}</p></div>
        <div className="primary-measure"><strong>{money(item.amountCents)}</strong><small>{item.probability}% probability</small></div>
      </header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="extended-workbench context-panel">
        <OperationalSection title="Commercial state" subtitle="Persisted mutation controls" badge={item.stage}>
          <div className="detail-form-grid">
            <label htmlFor="deal-stage">Deal stage
              <select id="deal-stage" value={stage} onChange={(event) => setStage(event.target.value as OpportunityStage)}>
                {stages.map((option) => <option key={option}>{option}</option>)}
              </select>
            </label>
            <label htmlFor="deal-probability">Probability
              <input id="deal-probability" type="number" min="0" max="100" value={probability} onChange={(event) => setProbability(Number(event.target.value))} />
            </label>
            <button type="button" onClick={() => void save()}>Save deal</button>
          </div>
        </OperationalSection>
        <OperationalSection title="Activity narrative" subtitle="Cross-system history assembled from a related table">
          <ol className="event-ledger">
            {item.history.map((event) => (
              <li key={event.id}><strong>{event.action}</strong><p>{event.detail}</p><small>{event.actor} · {event.createdAt}</small></li>
            ))}
          </ol>
        </OperationalSection>
      </div>
    </div>
  );
}

export function ForecastPage() {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [targets, setTargets] = useState<RevenueTarget[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.getForecast(), api.getRevenueTargets()])
      .then(([nextForecast, nextTargets]) => {
        setForecast(nextForecast);
        setTargets(nextTargets);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Forecast unavailable."),
      );
  }, []);

  if (!forecast && !error) return <Spinner label="Calculating forecast narratives…" />;

  return (
    <div className="fixture-page forecast-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Predictive revenue planning</span><h1>Forecast</h1><p>Compare weighted, committed, and at-risk revenue using the fixture pipeline.</p></div></header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      {forecast ? (
        <div className="context-metric-mosaic">
          {Object.entries({
            Pipeline: forecast.pipelineCents,
            Weighted: forecast.weightedCents,
            Commit: forecast.commitCents,
            "At risk": forecast.atRiskCents,
          }).map(([label, value]) => (
            <OperationalSection key={label} eyebrow={forecast.quarter} title={label}>
              <strong className="giant-number">{money(value)}</strong>
              <div className="confidence-orbit" aria-hidden="true"><span /></div>
            </OperationalSection>
          ))}
        </div>
      ) : null}
      <div className="table-wrap">
        <table>
          <thead><tr><th scope="col">Team</th><th scope="col">Target</th><th scope="col">Attained</th><th scope="col">Confidence</th><th scope="col">Attainment</th></tr></thead>
          <tbody>{targets.map((target) => (
            <tr key={target.team}><td>{target.team}</td><td>{money(target.targetCents)}</td><td>{money(target.attainedCents)}</td><td>{target.confidence}%</td><td>{Math.round(target.attainedCents / target.targetCents * 100)}%</td></tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
