import type { Activity } from "../types";

export function ActivityFeed({ items }: { items: Activity[] }) {
  return (
    <div className="activity-feed">
      {items.map((item) => (
        <div className="activity-item" key={item.id}>
          <span className="activity-avatar">{item.actor.slice(0, 2)}</span>
          <div>
            <p>
              <b>{item.actor}</b> {item.action}
            </p>
            <small>{item.detail}</small>
          </div>
          <time>{new Date(item.created_at).toLocaleDateString()}</time>
        </div>
      ))}
    </div>
  );
}

