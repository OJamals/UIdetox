import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type { DataConnector } from "../types";

export function DataHubPage() {
  const [connectors, setConnectors] = useState<DataConnector[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("Connector state is synchronized with the fixture API.");

  useEffect(() => {
    api.getDataConnectors()
      .then(setConnectors)
      .catch((reason) => setMessage(reason instanceof Error ? reason.message : "Data sources could not be loaded."))
      .finally(() => setLoading(false));
  }, []);

  const totalRecords = useMemo(() => connectors.reduce((sum, item) => sum + item.recordCount, 0), [connectors]);

  async function synchronize(item: DataConnector) {
    try {
      const saved = await api.syncConnector(item.id);
      setConnectors((current) => current.map((connector) => connector.id === saved.id ? saved : connector));
      setMessage(`${saved.name} synchronization started.`);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Synchronization could not be started.");
    }
  }

  if (loading) return <Spinner label="Loading data sources…" />;

  return (
    <div className="fixture-page data-hub-page">
      <header className="page-heading"><div><span className="eyebrow">Integration inventory</span><h1>Data hub</h1><p>Inspect provider ownership, record volume, destination, and synchronization state.</p></div></header>
      <p className="status-ribbon" role="status">{message}</p>
      <section className="portfolio-ledger" aria-labelledby="data-summary-title">
        <div className="primary-measure"><span className="eyebrow">Mapped records</span><h2 id="data-summary-title">{totalRecords.toLocaleString()}</h2></div>
        <dl className="measure-ledger"><div><dt>Sources</dt><dd>{connectors.length}</dd></div><div><dt>Healthy</dt><dd>{connectors.filter((item) => item.status === "healthy").length}</dd></div></dl>
      </section>

      <div className="connector-grid">
        {connectors.map((connector) => (
          <OperationalSection key={connector.id} title={connector.name} subtitle={connector.destination} badge={connector.status}>
            <dl className="detail-list">
              <div><dt>Provider</dt><dd>{connector.provider}</dd></div>
              <div><dt>Records</dt><dd>{connector.recordCount.toLocaleString()}</dd></div>
              <div><dt>Credential owner</dt><dd>{connector.credentials.owner}</dd></div>
              <div><dt>Last sync</dt><dd>{connector.lastSyncedAt || "No completed sync"}</dd></div>
            </dl>
            <button type="button" onClick={() => void synchronize(connector)}>Start synchronization</button>
          </OperationalSection>
        ))}
      </div>
    </div>
  );
}
