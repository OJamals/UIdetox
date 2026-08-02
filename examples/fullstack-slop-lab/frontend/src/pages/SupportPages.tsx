import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type {
  SlaPolicy,
  SupportCase,
  SupportCaseDetail,
  SupportMacro,
} from "../types";

export function SupportPage() {
  const [cases, setCases] = useState<SupportCase[]>([]);
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getSupportCases()
      .then(setCases)
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Cases unavailable."),
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner label="Loading customer support queue…" />;
  const visible = cases.filter((item) => filter === "all" || item.status === filter);

  return (
    <div className="fixture-page support-page slop-context-zone">
      <header className="page-heading">
        <div><span className="eyebrow">Customer support operations</span><h1>Support queue</h1><p>Triage conversations, SLA exposure, account context, and assigned ownership.</p></div>
        <label htmlFor="support-filter">Case state
          <select id="support-filter" value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="all">All states</option><option value="open">Open</option><option value="waiting">Waiting</option><option value="resolved">Resolved</option>
          </select>
        </label>
      </header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      <div className="support-summary-rack context-glow-band">
        <div><span>Open</span><strong>{cases.filter((item) => item.status === "open").length}</strong></div>
        <div><span>Urgent</span><strong>{cases.filter((item) => item.priority === "urgent").length}</strong></div>
        <div><span>Unassigned</span><strong>{cases.filter((item) => item.assignee === "Unassigned").length}</strong></div>
        <div><span>Average SLA</span><strong>{Math.round(cases.reduce((sum, item) => sum + item.slaMinutes, 0) / Math.max(cases.length, 1))}m</strong></div>
      </div>
      <section className="case-ledger context-panel" aria-label="Support cases">
        {visible.map((item) => (
          <article key={item.id} className="case-row">
            <div><span className={`status-pill ${item.priority}`}>{item.priority}</span><Link to={`/support/${item.id}`}>{item.title}</Link><small>{item.accountName}</small></div>
            <div><strong>{item.assignee}</strong><small>{item.status} · SLA {item.slaMinutes}m</small></div>
            <time>{item.lastReplyAt}</time>
          </article>
        ))}
      </section>
    </div>
  );
}

export function SupportCasePage() {
  const { caseId = "" } = useParams();
  const [item, setItem] = useState<SupportCaseDetail | null>(null);
  const [assignee, setAssignee] = useState("Unassigned");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .getSupportCase(caseId)
      .then((result) => {
        setItem(result);
        setAssignee(result.assignee);
      })
      .catch((reason) =>
        setNotice(reason instanceof Error ? reason.message : "Case unavailable."),
      )
      .finally(() => setLoading(false));
  }, [caseId]);

  async function assign() {
    if (!item) return;
    try {
      const saved = await api.assignSupportCase(item.id, assignee);
      setItem((current) => current ? { ...current, ...saved } : current);
      setNotice(`Assigned to ${saved.assignee}.`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Assignment failed.");
    }
  }

  async function close() {
    if (!item) return;
    const saved = await api.closeSupportCase(item.id);
    setItem((current) => current ? { ...current, ...saved } : current);
    setNotice("Case marked resolved.");
  }

  if (loading) return <Spinner label="Loading case conversation…" />;
  if (!item) return <p className="error-banner" role="alert">{notice}</p>;

  return (
    <div className="fixture-page support-detail-page slop-context-zone">
      <nav aria-label="Breadcrumb"><Link to="/support">Support</Link> / {item.id}</nav>
      <header className="page-heading"><div><span className="eyebrow">{item.accountName}</span><h1>{item.title}</h1><p>Opened {item.openedAt}. First-response target {item.slaMinutes} minutes.</p></div><span className={`status-pill ${item.priority}`}>{item.priority}</span></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="extended-workbench">
        <OperationalSection title="Conversation" badge={item.status} className="context-panel">
          <ol className="conversation-ledger">
            {item.messages.map((message) => (
              <li key={message.id}><strong>{message.author}</strong><span>{message.channel}</span><p>{message.body}</p><time>{message.createdAt}</time></li>
            ))}
          </ol>
        </OperationalSection>
        <OperationalSection title="Ownership" subtitle="Persisted support mutation" className="context-panel">
          <label htmlFor="case-assignee">Assignee
            <select id="case-assignee" value={assignee} onChange={(event) => setAssignee(event.target.value)}>
              <option>Unassigned</option><option>Mara Voss</option><option>Imani Cole</option><option>Theo Rami</option>
            </select>
          </label>
          <div className="decision-button-stack">
            <button type="button" onClick={() => void assign()}>Assign case</button>
            <button type="button" onClick={() => void close()}>Resolve case</button>
          </div>
        </OperationalSection>
      </div>
    </div>
  );
}

export function ServiceLevelsPage() {
  const [policies, setPolicies] = useState<SlaPolicy[]>([]);
  const [macros, setMacros] = useState<SupportMacro[]>([]);
  const [selectedMacro, setSelectedMacro] = useState<SupportMacro | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.getSlaPolicies(), api.getSupportMacros()])
      .then(([nextPolicies, nextMacros]) => {
        setPolicies(nextPolicies);
        setMacros(nextMacros);
        setSelectedMacro(nextMacros[0] || null);
      })
      .catch((reason) =>
        setError(reason instanceof Error ? reason.message : "Service policy data unavailable."),
      );
  }, []);

  if (!policies.length && !error) return <Spinner label="Loading service policy matrix…" />;

  return (
    <div className="fixture-page service-levels-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Operational promise management</span><h1>Service levels</h1><p>Compare support promises with the response language agents use at scale.</p></div></header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      <div className="context-metric-mosaic">
        {policies.map((policy) => (
          <OperationalSection key={policy.id} title={policy.name} badge={policy.priority} className="context-panel">
            <dl className="detail-list"><div><dt>First response</dt><dd>{policy.firstResponseMinutes} minutes</dd></div><div><dt>Resolution</dt><dd>{policy.resolutionMinutes} minutes</dd></div><div><dt>Coverage</dt><dd>{policy.coverage}</dd></div></dl>
          </OperationalSection>
        ))}
      </div>
      <div className="macro-browser context-panel">
        <section aria-labelledby="macro-list-title"><h2 id="macro-list-title">Response accelerators</h2>{macros.map((macro) => (
          <button
            type="button"
            aria-pressed={selectedMacro?.id === macro.id}
            className="macro-row"
            key={macro.id}
            onClick={() => setSelectedMacro(macro)}
          >
            <strong>{macro.title}</strong><small>{macro.usageCount} uses · {macro.owner}</small>
          </button>
        ))}</section>
        <article><span className="eyebrow">Selected macro preview</span><h3>{selectedMacro?.title}</h3><p>{selectedMacro?.bodyPreview}</p></article>
      </div>
    </div>
  );
}
