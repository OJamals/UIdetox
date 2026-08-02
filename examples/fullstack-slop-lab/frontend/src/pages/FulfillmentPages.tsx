import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { Spinner } from "../components/Spinner";
import type {
  CatalogCategory,
  CatalogItem,
  InventoryItem,
  InventoryLocation,
  Order,
  OrderDetail,
  Shipment,
} from "../types";

function money(cents: number) {
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
}

export function CatalogPage() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [categories, setCategories] = useState<CatalogCategory[]>([]);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    Promise.all([api.getCatalogItems(), api.getCatalogCategories()])
      .then(([nextItems, nextCategories]) => {
        setItems(nextItems);
        setCategories(nextCategories);
      })
      .catch((reason) => setNotice(reason instanceof Error ? reason.message : "Catalog unavailable."));
  }, []);

  async function archive(item: CatalogItem) {
    const saved = await api.archiveCatalogItem(item.id);
    setItems((current) => current.map((entry) => entry.id === saved.id ? saved : entry));
    setNotice(`${saved.name} archived.`);
  }

  if (!items.length && !notice) return <Spinner label="Loading commercial catalog…" />;
  return (
    <div className="fixture-page catalog-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Product operations</span><h1>Catalog</h1><p>Manage orderable platform, usage, and service offers across inconsistent inventory policies.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="support-summary-rack context-glow-band">{categories.map((category) => <div key={category.name}><span>{category.name}</span><strong>{category.activeCount}/{category.itemCount}</strong></div>)}</div>
      <div className="catalog-shelf">
        {items.map((item) => (
          <OperationalSection className="context-panel" key={item.id} eyebrow={item.sku} title={item.name} badge={item.status} footer={<small>{item.stockPolicy}</small>}>
            <strong className="plan-price">{money(item.priceCents)}</strong><p>{item.description}</p>
            <button type="button" disabled={item.status === "archived"} onClick={() => void archive(item)}>Archive offer</button>
          </OperationalSection>
        ))}
      </div>
    </div>
  );
}

export function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    api.getOrders().then(setOrders).catch((reason) => setError(reason instanceof Error ? reason.message : "Orders unavailable."));
  }, []);
  if (!orders.length && !error) return <Spinner label="Loading orders…" />;
  return (
    <div className="fixture-page orders-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Fulfillment ledger</span><h1>Orders</h1><p>Trace commercial commitments into line-level fulfillment work.</p></div></header>
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      <div className="table-wrap context-panel">
        <table><thead><tr><th scope="col">Order</th><th scope="col">Account</th><th scope="col">Status</th><th scope="col">Total</th><th scope="col">Promise</th><th scope="col">Channel</th></tr></thead><tbody>{orders.map((order) => (
          <tr key={order.id}><td><Link to={`/orders/${order.id}`}>{order.orderNo}</Link></td><td>{order.accountName}</td><td><span className="status-pill">{order.status}</span></td><td>{money(order.totalCents)}</td><td>{order.promisedAt}</td><td>{order.channel}</td></tr>
        ))}</tbody></table>
      </div>
    </div>
  );
}

export function OrderDetailPage() {
  const { orderId = "" } = useParams();
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.getOrder(orderId).then(setOrder).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Order unavailable.")).finally(() => setLoading(false));
  }, [orderId]);

  async function advance() {
    if (!order) return;
    const saved = await api.advanceOrder(order.id);
    setOrder((current) => current ? { ...current, ...saved } : current);
    setNotice(`Order advanced to ${saved.status}.`);
  }

  if (loading) return <Spinner label="Loading order lineage…" />;
  if (!order) return <p className="error-banner" role="alert">{notice}</p>;
  return (
    <div className="fixture-page order-detail-page slop-context-zone">
      <nav aria-label="Breadcrumb"><Link to="/orders">Orders</Link> / {order.orderNo}</nav>
      <header className="page-heading"><div><span className="eyebrow">{order.accountName}</span><h1>{order.orderNo}</h1><p>Created {order.createdAt}; promised {order.promisedAt}; channel {order.channel}.</p></div><div className="primary-measure"><strong>{money(order.totalCents)}</strong><small>{order.status}</small></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="table-wrap context-panel">
        <table aria-label="Order lines"><thead><tr><th scope="col">SKU</th><th scope="col">Item</th><th scope="col">Quantity</th><th scope="col">Unit price</th><th scope="col">Extended</th></tr></thead><tbody>{order.lines.map((line) => (
          <tr key={line.id}><td>{line.sku}</td><td>{line.name}</td><td>{line.quantity}</td><td>{money(line.unitPriceCents)}</td><td>{money(line.quantity * line.unitPriceCents)}</td></tr>
        ))}</tbody></table>
      </div>
      <button type="button" onClick={() => void advance()} disabled={order.status === "delivered"}>Advance order</button>
    </div>
  );
}

export function InventoryPage() {
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [locations, setLocations] = useState<InventoryLocation[]>([]);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    Promise.all([api.getInventory(), api.getInventoryLocations()]).then(([nextItems, nextLocations]) => {
      setItems(nextItems); setLocations(nextLocations);
    }).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Inventory unavailable."));
  }, []);

  async function recount(item: InventoryItem) {
    const saved = await api.recountInventory(item.id);
    setItems((current) => current.map((entry) => entry.id === saved.id ? saved : entry));
    setNotice(`${saved.sku} recounted.`);
  }

  if (!items.length && !notice) return <Spinner label="Reconciling inventory…" />;
  return (
    <div className="fixture-page inventory-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Inventory control</span><h1>Inventory</h1><p>Compare reserved, available, and reorder quantities across fulfillment locations.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="support-summary-rack context-glow-band">{locations.map((location) => <div key={location.name}><span>{location.name}</span><strong>{location.availableUnits}</strong><small>{location.attentionCount} need attention</small></div>)}</div>
      <div className="table-wrap context-panel"><table><thead><tr><th scope="col">SKU</th><th scope="col">Item</th><th scope="col">Location</th><th scope="col">On hand</th><th scope="col">Reserved</th><th scope="col">Available</th><th scope="col">Status</th><th scope="col">Action</th></tr></thead><tbody>{items.map((item) => (
        <tr key={item.id}><td>{item.sku}</td><td>{item.name}</td><td>{item.location}</td><td>{item.onHand}</td><td>{item.reserved}</td><td>{item.available}</td><td><span className={`status-pill ${item.status}`}>{item.status}</span></td><td><button type="button" onClick={() => void recount(item)}>Recount</button></td></tr>
      ))}</tbody></table></div>
    </div>
  );
}

export function ShipmentsPage() {
  const [shipments, setShipments] = useState<Shipment[]>([]);
  const [notice, setNotice] = useState("");
  useEffect(() => {
    api.getShipments().then(setShipments).catch((reason) => setNotice(reason instanceof Error ? reason.message : "Shipments unavailable."));
  }, []);

  async function hold(item: Shipment) {
    const saved = await api.holdShipment(item.id);
    setShipments((current) => current.map((entry) => entry.id === saved.id ? saved : entry));
    setNotice(`${saved.orderNo} placed on hold.`);
  }

  if (!shipments.length && !notice) return <Spinner label="Loading carrier events…" />;
  return (
    <div className="fixture-page shipments-page slop-context-zone">
      <header className="page-heading"><div><span className="eyebrow">Delivery intelligence</span><h1>Shipments</h1><p>Monitor labels, exceptions, carrier promises, and manually reconciled tracking references.</p></div></header>
      {notice ? <p className="status-ribbon" role="status">{notice}</p> : null}
      <div className="shipment-track context-panel">{shipments.map((item) => (
        <article key={item.id}><span className={`status-pill ${item.status}`}>{item.status}</span><h2>{item.orderNo}</h2><p>{item.carrier}</p><code>{item.trackingNo}</code><small>{item.etaAt ? `ETA ${item.etaAt}` : "No ETA"} {item.holdReason ? `· ${item.holdReason}` : ""}</small><button type="button" disabled={item.status === "held"} onClick={() => void hold(item)}>Hold shipment</button></article>
      ))}</div>
    </div>
  );
}
