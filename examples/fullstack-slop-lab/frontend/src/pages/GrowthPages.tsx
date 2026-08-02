import { useEffect, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type {
  Attribution,
  Campaign,
  ContentAsset,
  Segment,
  Survey,
  SurveyResult,
} from "../types";

function money(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api.getCampaigns().then(setCampaigns).catch((reason) => setError(reason instanceof Error ? reason.message : "Campaigns unavailable."));
  }, []);

  async function launch(campaign: Campaign) {
    setError("");
    try {
      const saved = await api.launchCampaign(campaign.id);
      setCampaigns((current) => current.map((item) => item.id === saved.id ? saved : item));
      setMessage(`${saved.name} launched.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Campaign launch failed.");
    }
  }

  async function pause(campaign: Campaign) {
    const saved = await api.pauseCampaign(campaign.id);
    setCampaigns((current) => current.map((item) => item.id === saved.id ? saved : item));
    setMessage(`${saved.name} paused.`);
  }

  if (!campaigns.length && !error) return <Spinner label="Loading growth orchestration…" />;
  return (
    <div className="fixture-page campaigns-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Growth orchestration studio</span><h1>Campaigns</h1><p>Coordinate audience, spend, channel, ownership, and strategic narrative from one view.</p></div><button className="celebration-trigger" type="button">Draft launch brief</button></header>
      {message ? <p className="status-ribbon" role="status">{message}</p> : null}
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      <div className="campaign-board context-glow-band">{campaigns.map((campaign) => (
        <OperationalSection key={campaign.id} title={campaign.name} eyebrow={campaign.channel} badge={campaign.status} className="context-panel">
          <dl className="detail-list"><div><dt>Audience</dt><dd>{campaign.audienceSize.toLocaleString()}</dd></div><div><dt>Budget</dt><dd>{money(campaign.budgetCents)}</dd></div><div><dt>Owner</dt><dd>{campaign.owner}</dd></div><div><dt>Schedule</dt><dd>{campaign.scheduledAt || "Not scheduled"}</dd></div></dl>
          <div className="decision-button-stack">
            <button type="button" aria-label={`Launch ${campaign.name}`} onClick={() => void launch(campaign)}>Launch</button>
            <button type="button" onClick={() => void pause(campaign)}>Pause</button>
          </div>
        </OperationalSection>
      ))}</div>
    </div>
  );
}

export function SegmentsPage() {
  const [segments, setSegments] = useState<Segment[]>([]);
  const [attribution, setAttribution] = useState<Attribution[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([api.getSegments(), api.getAttribution()]).then(([nextSegments, nextAttribution]) => {
      setSegments(nextSegments); setAttribution(nextAttribution);
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "Audience intelligence unavailable."));
  }, []);
  if (!segments.length && !error) return <Spinner label="Resolving audience definitions…" />;
  return (
    <div className="fixture-page segments-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Audience intelligence</span><h1>Segments</h1><p>Inspect query definitions, refresh state, and competing attribution narratives.</p></div></header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      <div className="segment-grid">{segments.map((segment) => (
        <OperationalSection key={segment.id} title={segment.name} badge={segment.refreshStatus} className="context-panel"><strong className="giant-number">{segment.memberCount.toLocaleString()}</strong><p className="clipped-definition">{segment.definition}</p><small>{segment.owner}</small></OperationalSection>
      ))}</div>
      <OperationalSection title="Attribution perspectives" subtitle="All models are presented with equal confidence styling" className="context-glow-band">
        <div className="context-metric-mosaic">{attribution.map((item) => <div key={item.model}><h3>{item.model}</h3><strong>{money(item.influencedPipelineCents)}</strong><p>{item.confidence}% confidence · {item.windowDays} day window</p></div>)}</div>
      </OperationalSection>
    </div>
  );
}

export function ContentLibraryPage() {
  const [assets, setAssets] = useState<ContentAsset[]>([]);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    api.getContentAssets().then(setAssets).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Content unavailable."));
  }, []);
  async function publish(asset: ContentAsset) {
    const saved = await api.publishContentAsset(asset.id);
    setAssets((current) => current.map((item) => item.id === saved.id ? saved : item));
    setNotice(`${saved.title} published.`);
  }
  if (!assets.length && !notice) return <Spinner label="Loading content intelligence…" />;
  return (
    <div className="fixture-page content-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Content operations</span><h1>Content library</h1><p>Coordinate reusable narratives across campaigns, journeys, and sales motions.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="content-wall context-panel">{assets.map((asset) => (
        <article key={asset.id}><span className="eyebrow">{asset.kind}</span><h2>{asset.title}</h2><p><span className="status-pill">{asset.status}</span> {asset.usageCount} placements</p><small>{asset.owner} · {asset.updatedAt}</small><button type="button" disabled={asset.status === "published"} onClick={() => void publish(asset)}>Publish everywhere</button></article>
      ))}</div>
    </div>
  );
}

export function SurveysPage() {
  const [surveys, setSurveys] = useState<Survey[]>([]);
  const [results, setResults] = useState<SurveyResult[]>([]);
  const [selected, setSelected] = useState<Survey | null>(null);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    api.getSurveys().then((items) => { setSurveys(items); setSelected(items[0] || null); }).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Surveys unavailable."));
  }, []);
  async function close(survey: Survey) {
    const saved = await api.closeSurvey(survey.id);
    setSurveys((current) => current.map((item) => item.id === saved.id ? saved : item));
    setSelected(saved);
    setNotice(`${saved.title} closed.`);
  }
  async function inspect(survey: Survey) {
    setSelected(survey);
    setResults(await api.getSurveyResults(survey.id));
  }
  if (!surveys.length && !notice) return <Spinner label="Loading feedback rituals…" />;
  return (
    <div className="fixture-page surveys-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Voice of customer</span><h1>Surveys</h1><p>Monitor response volume, completion, and narratively grouped answer distributions.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="extended-workbench">
        <section className="survey-stack context-panel" aria-label="Survey list">{surveys.map((survey) => (
          <article key={survey.id}><span className="status-pill">{survey.status}</span><h2>{survey.title}</h2><p>{survey.responseCount} responses · {survey.completionRate}% completion</p><small>{survey.owner}</small><div className="decision-button-stack"><button type="button" onClick={() => void inspect(survey)}>View results</button><button type="button" disabled={survey.status === "closed"} onClick={() => void close(survey)}>Close survey</button></div></article>
        ))}</section>
        <OperationalSection title={selected?.title || "Survey results"} subtitle="Response distribution" className="context-glow-band">{results.length ? results.map((result) => <div className="survey-result" key={result.label}><span>{result.label}</span><strong>{result.percent}%</strong><div style={{ width: `${result.percent}%` }} /></div>) : <p>Select a survey to load its answer distribution.</p>}</OperationalSection>
      </div>
    </div>
  );
}
