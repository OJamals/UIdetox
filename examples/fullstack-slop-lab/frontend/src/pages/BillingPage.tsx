import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Spinner } from "../components/Spinner";
import type { Invoice } from "../types";

export function BillingPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getInvoices()
      .then(setInvoices)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Invoices could not be loaded."))
      .finally(() => setLoading(false));
  }, []);

  const visibleInvoices = useMemo(
    () => invoices.filter((invoice) => status === "all" || invoice.status === status),
    [invoices, status],
  );
  const totalCents = useMemo(() => visibleInvoices.reduce((sum, invoice) => sum + invoice.amountCents, 0), [visibleInvoices]);

  function downloadInvoice(invoice: Invoice) {
    const content = ["invoice,account,amount,status,created,due", [
      invoice.invoiceNo,
      invoice.accountName,
      (invoice.amountCents / 100).toFixed(2),
      invoice.status,
      invoice.createdAt,
      invoice.dueAt,
    ].join(",")].join("\n");
    const url = URL.createObjectURL(new Blob([content], { type: "text/csv" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${invoice.invoiceNo}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <Spinner label="Loading invoices…" />;

  return (
    <div className="fixture-page billing-page">
      <header className="page-heading">
        <div>
          <span className="eyebrow">Accounts receivable</span>
          <h1>Billing</h1>
          <p>Review invoice status and export individual records from the mapped billing contract.</p>
        </div>
        <label htmlFor="invoice-status">Status
          <select id="invoice-status" value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="all">All invoices</option>
            <option value="open">Open</option>
            <option value="paid">Paid</option>
            <option value="overdue">Overdue</option>
          </select>
        </label>
      </header>

      {error ? <div className="error-banner" role="alert">{error}</div> : null}

      <section className="portfolio-ledger" aria-labelledby="billing-total-title">
        <div className="primary-measure">
          <span className="eyebrow">Visible invoice total</span>
          <h2 id="billing-total-title">${(totalCents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}</h2>
          <p>{visibleInvoices.length} records in the current filter.</p>
        </div>
      </section>

      <div className="table-wrap">
        <table className="tabular-nums">
          <thead><tr><th scope="col">Invoice</th><th scope="col">Account</th><th scope="col">Amount</th><th scope="col">Status</th><th scope="col">Dates</th><th scope="col">Export</th></tr></thead>
          <tbody>
            {visibleInvoices.map((invoice) => (
              <tr key={invoice.id}>
                <td>{invoice.invoiceNo}</td>
                <td>{invoice.accountName}</td>
                <td>${(invoice.amountCents / 100).toFixed(2)}</td>
                <td><span className={`status-pill ${invoice.status}`}>{invoice.status}</span></td>
                <td>Issued {invoice.createdAt}<br />Due {invoice.dueAt}</td>
                <td><button type="button" onClick={() => downloadInvoice(invoice)}>Download CSV</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
