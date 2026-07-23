import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { RiskMeter } from "../components/RiskMeter";
import { Spinner } from "../components/Spinner";
import type { CustomerProfile } from "../types";

export function CustomersPage() {
  const [customers, setCustomers] = useState<CustomerProfile[]>([]);
  const [selected, setSelected] = useState<CustomerProfile | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("Account health is synchronized with the fixture API.");

  useEffect(() => {
    api.getCustomers().then((items) => {
      setCustomers(items);
      setSelected(items[0] || null);
    }).catch((reason) => {
      setNotice(reason instanceof Error ? reason.message : "Accounts could not be loaded.");
    }).finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return customers.filter((customer) => `${customer.displayName} ${customer.primaryContact.email} ${customer.owner.name}`.toLowerCase().includes(normalized));
  }, [customers, query]);
  const totalRevenue = customers.reduce((sum, item) => sum + item.annualRevenueCents, 0);
  const averageHealth = customers.length ? Math.round(customers.reduce((sum, item) => sum + item.healthScore, 0) / customers.length) : 0;

  async function rescue(customer: CustomerProfile) {
    try {
      const saved = await api.updateCustomerHealth(customer.id, 99);
      setCustomers((current) => current.map((item) => item.id === saved.id ? saved : item));
      setSelected(saved);
      setNotice(`${saved.displayName} health updated to ${saved.healthScore}.`);
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : "Account health could not be updated.");
    }
  }

  if (loading) return <Spinner label="Loading accounts…" />;

  return (
    <div className="fixture-page customers-page">
      <header className="page-heading"><div><span className="eyebrow">Account registry</span><h1>Customers</h1><p>Review lifecycle, revenue, ownership, and persisted health scores.</p></div></header>
      <p className="status-ribbon" role="status">{notice}</p>
      <section className="portfolio-ledger" aria-labelledby="customer-summary-title">
        <div className="primary-measure"><span className="eyebrow">Managed revenue</span><h2 id="customer-summary-title">${(totalRevenue / 100).toLocaleString()}</h2></div>
        <dl className="measure-ledger"><div><dt>Accounts</dt><dd>{customers.length}</dd></div><div><dt>Average health</dt><dd>{averageHealth}%</dd></div></dl>
      </section>

      <label htmlFor="customer-search">Search accounts</label>
      <input id="customer-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Account, contact, or owner" />

      <div className="customer-command-grid">
        <div className="customer-table">
          {visible.map((customer) => (
            <button type="button" className="customer-table-row" key={customer.id} onClick={() => setSelected(customer)}>
              <span><strong>{customer.displayName}</strong><small>{customer.primaryContact.email}</small></span>
              <span className="status-pill">{customer.lifecycleStage}</span>
              <RiskMeter value={customer.healthScore} caption="Health" />
              <b>${(customer.annualRevenueCents / 100).toLocaleString()}</b>
              <span>{customer.owner.name}</span>
              <time>{customer.lastTouchAt || "No recorded touch"}</time>
            </button>
          ))}
        </div>

        <OperationalSection title={selected?.displayName || "No account selected"} subtitle={selected ? `Primary contact: ${selected.primaryContact.name}` : undefined} badge={selected?.lifecycleStage}>
          {selected ? (
            <div className="customer-detail-copy">
              <p>{selected.notes}</p>
              <dl className="detail-list"><div><dt>Owner</dt><dd>{selected.owner.name}</dd></div><div><dt>Health score</dt><dd>{selected.healthScore}%</dd></div></dl>
              <button type="button" onClick={() => void rescue(selected)}>Set health to 99</button>
            </div>
          ) : <p>Select an account from the registry.</p>}
        </OperationalSection>
      </div>
    </div>
  );
}
