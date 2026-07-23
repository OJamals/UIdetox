import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { DecisionBadge } from "../components/DecisionBadge";
import { OperationalSection } from "../components/MagicCard";
import { RiskMeter } from "../components/RiskMeter";
import { Spinner } from "../components/Spinner";
import type { ApprovalRequest } from "../types";

export function ApprovalsPage() {
  const [items, setItems] = useState<ApprovalRequest[]>([]);
  const [selected, setSelected] = useState<ApprovalRequest | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("Approval state is synchronized with the fixture API.");

  useEffect(() => {
    api.getApprovalRequests().then((results) => {
      setItems(results);
      setSelected(results[0] || null);
    }).catch((reason) => {
      setNotice(reason instanceof Error ? reason.message : "Approval requests could not be loaded.");
    }).finally(() => setLoading(false));
  }, []);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => `${item.title} ${item.kind} ${item.requestor.name}`.toLowerCase().includes(normalized));
  }, [items, query]);
  const pending = items.filter((item) => item.status === "pending" || item.status === "needs-info").length;

  async function decide(decision: "approved" | "rejected" | "needs-info") {
    if (!selected) return;
    try {
      const saved = await api.decideApproval(selected.id, decision);
      setItems((current) => current.map((item) => item.id === saved.id ? saved : item));
      setSelected(saved);
      setNotice(`Decision saved as ${saved.status}.`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Decision could not be saved.");
    }
  }

  if (loading) return <Spinner label="Loading approvals…" />;

  return (
    <div className="fixture-page approvals-page">
      <header className="page-heading">
        <div><span className="eyebrow">Governance queue</span><h1>Approvals</h1><p>Review context and record one of the decisions supported by the backend contract.</p></div>
        <div className="primary-measure"><strong>{pending}</strong><small>open decisions</small></div>
      </header>
      <p className="status-ribbon" role="status">{notice}</p>

      <div className="approval-workbench">
        <section className="approval-queue" aria-labelledby="approval-queue-title">
          <div className="queue-toolbar">
            <label htmlFor="approval-search" id="approval-queue-title">Search approvals</label>
            <input id="approval-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, type, or requestor" />
          </div>
          {visibleItems.map((item) => (
            <button type="button" className={`approval-row ${selected?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => setSelected(item)}>
              <DecisionBadge state={item.status} risk={item.riskScore} />
              <span><strong>{item.title}</strong><small>{item.kind} · {item.requestor.name}</small></span>
              <time>{item.submittedAt}</time>
            </button>
          ))}
        </section>

        <OperationalSection title={selected?.title || "No decision selected"} subtitle={selected?.kind} badge={selected?.status}>
          {selected ? (
            <div className="approval-detail-body">
              <RiskMeter value={selected.riskScore} caption="Recorded risk" />
              <p>{selected.context}</p>
              <dl className="detail-list"><div><dt>Requestor</dt><dd>{selected.requestor.name}</dd></div><div><dt>Department</dt><dd>{selected.requestor.department}</dd></div></dl>
              <div className="reviewer-pills">{selected.reviewers.length ? selected.reviewers.map((reviewer) => <span key={reviewer.id}>{reviewer.name}</span>) : <span>No reviewers assigned</span>}</div>
              <div className="decision-button-stack">
                <button type="button" onClick={() => void decide("approved")}>Approve</button>
                <button type="button" onClick={() => void decide("rejected")}>Reject</button>
                <button type="button" onClick={() => void decide("needs-info")}>Request information</button>
              </div>
            </div>
          ) : <p>Select a request from the queue.</p>}
        </OperationalSection>
      </div>
    </div>
  );
}
