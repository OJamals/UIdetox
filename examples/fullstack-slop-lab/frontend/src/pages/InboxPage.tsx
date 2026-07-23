import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { OperationalSection } from "../components/MagicCard";
import { QuickComposer } from "../components/QuickComposer";
import { Spinner } from "../components/Spinner";
import type { Notification } from "../types";

export function InboxPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [selected, setSelected] = useState<Notification | null>(null);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState("Notification state is synchronized with the fixture API.");

  useEffect(() => {
    api.getNotifications().then((items) => {
      setNotifications(items);
      setSelected(items[0] || null);
    }).catch((reason) => {
      setResult(reason instanceof Error ? reason.message : "Notifications could not be loaded.");
    }).finally(() => setLoading(false));
  }, []);

  const visible = useMemo(() => notifications.filter((item) => {
    const matchesFilter = filter === "all" || !item.read;
    const haystack = `${item.subject} ${item.body} ${item.sender.displayName}`.toLowerCase();
    return matchesFilter && haystack.includes(query.trim().toLowerCase());
  }), [filter, notifications, query]);

  async function markRead(item: Notification) {
    try {
      const saved = await api.markNotificationRead(item.id);
      setNotifications((current) => current.map((value) => value.id === saved.id ? saved : value));
      setSelected(saved);
      setResult("Read status saved.");
    } catch (reason) {
      setResult(reason instanceof Error ? reason.message : "Read status could not be saved.");
    }
  }

  if (loading) return <Spinner label="Loading notifications…" />;

  return (
    <div className="fixture-page inbox-page">
      <header className="page-heading">
        <div><span className="eyebrow">Notification register</span><h1>Inbox</h1><p>Search incoming workspace events and persist read state.</p></div>
      </header>
      <QuickComposer onSend={(message) => setResult(`Draft prepared locally: ${message}`)} />
      <div className="inbox-toolbar">
        <label htmlFor="notification-search">Search</label>
        <input id="notification-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Subject, sender, or body" />
        <label htmlFor="notification-filter">Visibility</label>
        <select id="notification-filter" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">All notifications</option><option value="unread">Unread only</option>
        </select>
        <small role="status">{result}</small>
      </div>

      <div className="inbox-layout">
        <nav aria-label="Notifications" className="notification-list">
          {visible.map((item) => (
            <button type="button" className={`notification-preview ${item.read ? "read" : "unread"}`} onClick={() => setSelected(item)} key={item.id}>
              <span className="notification-avatar" aria-hidden="true">{item.sender.displayName.slice(0, 2)}</span>
              <span><b>{item.subject}</b><small>{item.body}</small></span>
              <time>{item.createdAt}</time>
            </button>
          ))}
        </nav>
        <OperationalSection title={selected?.subject || "No notification selected"} subtitle={selected ? `From ${selected.sender.displayName}` : undefined} badge={selected?.read ? "Read" : "Unread"}>
          {selected ? (
            <div className="message-document">
              <p>{selected.body}</p>
              {!selected.read ? <button type="button" onClick={() => void markRead(selected)}>Mark as read</button> : <small>Read state is current.</small>}
            </div>
          ) : <p>Select a notification from the list.</p>}
        </OperationalSection>
      </div>
    </div>
  );
}
