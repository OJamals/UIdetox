import { useEffect, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type {
  AuditEvent,
  FeatureFlag,
  Incident,
  MarketplaceApp,
  UsageMetric,
  WorkItem,
} from "../types";

export function AuditLogPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [selected, setSelected] = useState<AuditEvent | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.getAuditEvents().then((items) => { setEvents(items); setSelected(items[0] || null); }).catch((reason) => setError(reason instanceof Error ? reason.message : "Audit history unavailable."));
  }, []);
  if (!events.length && !error) return <Spinner label="Loading audit chronology…" />;
  return (
    <div className="fixture-page audit-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Workspace governance</span><h1>Audit log</h1><p>Review actor, action, resource, network hint, and narrative evidence across synthetic changes.</p></div></header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      <div className="extended-workbench">
        <section className="audit-stream context-panel" aria-label="Audit events">{events.map((event) => (
          <button type="button" key={event.id} onClick={() => setSelected(event)}><span>{event.action}</span><strong>{event.resource}</strong><small>{event.actor} · {event.createdAt}</small></button>
        ))}</section>
        <OperationalSection title={selected?.action || "Select an event"} badge={selected?.ipHint} className="context-glow-band"><h3>{selected?.resource}</h3><p>{selected?.detail}</p><small>{selected?.actor} · {selected?.createdAt}</small></OperationalSection>
      </div>
    </div>
  );
}

export function FeatureFlagsPage() {
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    api.getFeatureFlags().then(setFlags).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Flags unavailable."));
  }, []);
  async function toggle(flag: FeatureFlag) {
    const saved = await api.updateFeatureFlag(flag.key, !flag.enabled);
    setFlags((current) => current.map((item) => item.key === saved.key ? saved : item));
    setNotice(`${saved.title} ${saved.enabled ? "enabled" : "disabled"}.`);
  }
  if (!flags.length && !notice) return <Spinner label="Loading rollout controls…" />;
  return (
    <div className="fixture-page flags-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Progressive delivery controls</span><h1>Feature flags</h1><p>Inspect owner, rollout, and audience semantics before changing synthetic workspace behavior.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="flag-matrix context-glow-band">{flags.map((flag) => (
        <OperationalSection key={flag.key} title={flag.title} eyebrow={flag.key} badge={flag.enabled ? "enabled" : "disabled"} className="context-panel">
          <p className="clipped-definition">{flag.audience}</p><dl className="detail-list"><div><dt>Rollout</dt><dd>{flag.rolloutPercent}%</dd></div><div><dt>Owner</dt><dd>{flag.owner}</dd></div></dl>
          <label className="switch-row"><input type="checkbox" checked={flag.enabled} onChange={() => void toggle(flag)} /><span>Enable flag</span></label>
        </OperationalSection>
      ))}</div>
    </div>
  );
}

export function ServiceHealthPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [usage, setUsage] = useState<UsageMetric[]>([]);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    Promise.all([api.getIncidents(), api.getPlatformUsage()]).then(([nextIncidents, nextUsage]) => { setIncidents(nextIncidents); setUsage(nextUsage); }).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Platform telemetry unavailable."));
  }, []);
  async function acknowledge(incident: Incident) {
    const saved = await api.acknowledgeIncident(incident.id);
    setIncidents((current) => current.map((item) => item.id === saved.id ? saved : item));
    setNotice(`${saved.title} acknowledged.`);
  }
  if (!incidents.length && !notice) return <Spinner label="Loading platform telemetry…" />;
  return (
    <div className="fixture-page health-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Platform control plane</span><h1>Service health</h1><p>Connect incident state with usage pressure and affected service ownership.</p></div><span className="live-orbit">Live</span></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="context-metric-mosaic">{usage.map((metric) => (
        <OperationalSection key={metric.metric} title={metric.metric} badge={`${metric.trend}% trend`} className="context-panel"><strong className="giant-number">{metric.value.toLocaleString()}</strong><p>{metric.value > metric.limit ? "Above" : "Within"} {metric.limit.toLocaleString()} {metric.unit} limit.</p><meter aria-label={`${metric.metric} usage`} className="usage-track" max={metric.limit} min={0} value={Math.min(metric.value, metric.limit)} /></OperationalSection>
      ))}</div>
      <section className="incident-stack context-glow-band" aria-label="Active incidents">{incidents.map((incident) => (
        <article key={incident.id}><span className={`status-pill ${incident.severity}`}>{incident.severity}</span><h2>{incident.title}</h2><p>{incident.affectedService}</p><small>{incident.startedAt} · {incident.status}</small><button type="button" disabled={incident.acknowledged} onClick={() => void acknowledge(incident)}>{incident.acknowledged ? "Acknowledged" : "Acknowledge incident"}</button></article>
      ))}</section>
    </div>
  );
}

export function MarketplacePage() {
  const [apps, setApps] = useState<MarketplaceApp[]>([]);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    api.getMarketplaceApps().then(setApps).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Marketplace unavailable."));
  }, []);
  async function install(app: MarketplaceApp) {
    const saved = await api.installMarketplaceApp(app.id);
    setApps((current) => current.map((item) => item.id === saved.id ? saved : item));
    setNotice(`${saved.name} installed with ${saved.permissions.length} permissions.`);
  }
  if (!apps.length && !notice) return <Spinner label="Loading integration marketplace…" />;
  return (
    <div className="fixture-page marketplace-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Integration ecosystem</span><h1>Marketplace</h1><p>Discover deeply empowering extensions and review their broad synthetic permission requests.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="marketplace-grid">{apps.map((app) => (
        <OperationalSection key={app.id} title={app.name} eyebrow={app.category} badge={app.installed ? "installed" : "available"} className="context-panel"><p>{app.description}</p><div className="skill-pills">{app.permissions.map((permission) => <span key={permission}>{permission}</span>)}</div><button type="button" disabled={app.installed} onClick={() => void install(app)}>{app.installed ? "Installed" : "Install app"}</button></OperationalSection>
      ))}</div>
    </div>
  );
}

export function WorkQueuePage() {
  const [items, setItems] = useState<WorkItem[]>([]);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    api.getWorkQueue().then(setItems).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Work queue unavailable."));
  }, []);
  async function claim(item: WorkItem) {
    const saved = await api.claimWorkItem(item.id);
    setItems((current) => current.map((entry) => entry.id === saved.id ? saved : entry));
    setNotice(`${saved.title} claimed.`);
  }
  async function complete(item: WorkItem) {
    const saved = await api.completeWorkItem(item.id);
    setItems((current) => current.map((entry) => entry.id === saved.id ? saved : entry));
    setNotice(`${saved.title} completed.`);
  }
  if (!items.length && !notice) return <Spinner label="Composing unified work queue…" />;
  return (
    <div className="fixture-page work-queue-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Unified action surface</span><h1>Work queue</h1><p>Consolidate revenue, service, governance, and fulfillment actions into one prioritized ledger.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <section className="work-queue context-panel" aria-label="Work items">{items.map((item) => (
        <article key={item.id}><strong className="queue-priority">{item.priority}</strong><div><span className="eyebrow">{item.kind} · {item.source}</span><h2>{item.title}</h2><p>{item.owner || "No owner"} · due {item.dueAt}</p></div><span className="status-pill">{item.status}</span><div className="decision-button-stack"><button type="button" disabled={item.status !== "unclaimed"} onClick={() => void claim(item)}>Claim</button><button type="button" disabled={item.status === "done"} onClick={() => void complete(item)}>Complete</button></div></article>
      ))}</section>
    </div>
  );
}
