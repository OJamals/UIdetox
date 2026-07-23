import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { QuickComposer } from "../components/QuickComposer";
import { Spinner } from "../components/Spinner";
import type { Automation } from "../types";

export function AutomationsPage() {
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("Workflow state is synchronized with the fixture API.");

  useEffect(() => {
    api.getAutomations()
      .then(setAutomations)
      .catch((reason) => setMessage(reason instanceof Error ? reason.message : "Workflows could not be loaded."))
      .finally(() => setLoading(false));
  }, []);

  const activeCount = useMemo(() => automations.filter((item) => item.enabled).length, [automations]);

  async function pause(id: number) {
    setMessage("Pausing workflow…");
    try {
      const updated = await api.pauseAutomation(id);
      setAutomations((current) => current.map((item) => item.id === id ? updated : item));
      setMessage(`Paused ${updated.name}.`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Workflow could not be paused.");
    }
  }

  if (loading) return <Spinner label="Loading workflows…" />;

  return (
    <div className="fixture-page automations-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Workflow registry</span>
          <h1>Automations</h1>
          <p>Inspect triggers, schedules, destinations, and persisted run state.</p>
        </div>
      </header>

      <QuickComposer onSend={(value) => setMessage(`Draft prepared locally: ${value}`)} />
      <p className="status-ribbon" role="status">{message}</p>

      <dl className="measure-ledger">
        <div><dt>Registered workflows</dt><dd>{automations.length}</dd></div>
        <div><dt>Active</dt><dd>{activeCount}</dd></div>
        <div><dt>Paused</dt><dd>{automations.length - activeCount}</dd></div>
      </dl>

      <div className="automation-list">
        {automations.map((automation) => (
          <OperationalSection
            key={automation.id}
            title={automation.name}
            subtitle={automation.destination}
            badge={automation.enabled ? "Active" : "Paused"}
            footer={automation.enabled ? (
              <button type="button" onClick={() => void pause(automation.id)}>Pause workflow</button>
            ) : <small>No action available while paused.</small>}
          >
            <dl className="detail-list">
              <div><dt>Trigger</dt><dd>{automation.trigger}</dd></div>
              <div><dt>Schedule</dt><dd>{automation.schedule}</dd></div>
              <div><dt>Last run</dt><dd>{automation.lastRun || "No recorded run"}</dd></div>
            </dl>
          </OperationalSection>
        ))}
      </div>
    </div>
  );
}
