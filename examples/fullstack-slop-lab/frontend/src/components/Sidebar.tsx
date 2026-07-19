import { NavLink } from "react-router-dom";

const items = [
  { to: "/", icon: "✨", label: "Dashboard" },
  { to: "/projects", icon: "🚀", label: "Projects" },
  { to: "/analytics", icon: "📊", label: "Analytics" },
  { to: "/team", icon: "👥", label: "Team" },
  { to: "/settings", icon: "⚙️", label: "Settings" },
];

export function Sidebar() {
  return (
    <aside className="sidebar glass-card">
      <div className="logo">
        <span className="logo-orb">N</span>
        <span>NexusFlow</span>
        <span className="ai-pill">AI</span>
      </div>
      <nav>
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) => (isActive ? "nav-item active" : "nav-item")}
          >
            <span>{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="upgrade-card">
        <span>💎</span>
        <b>Unlock Pro</b>
        <p>Supercharge everything with magical AI.</p>
        <button>Upgrade now</button>
      </div>
    </aside>
  );
}

