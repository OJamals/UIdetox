import { NavLink } from "react-router-dom";

const sections = [
  {
    label: "Operate",
    items: [
      { to: "/", marker: "01", label: "Overview" },
      { to: "/projects", marker: "02", label: "Projects" },
      { to: "/automations", marker: "03", label: "Automations" },
      { to: "/inbox", marker: "04", label: "Inbox" },
      { to: "/journeys", marker: "05", label: "Journeys" },
    ],
  },
  {
    label: "Understand",
    items: [
      { to: "/analytics", marker: "06", label: "Analytics" },
      { to: "/customers", marker: "07", label: "Customers" },
      { to: "/experiments", marker: "08", label: "Experiments" },
      { to: "/data-hub", marker: "09", label: "Data sources" },
    ],
  },
  {
    label: "Administer",
    items: [
      { to: "/approvals", marker: "10", label: "Approvals" },
      { to: "/billing", marker: "11", label: "Billing" },
      { to: "/team", marker: "12", label: "Team" },
      { to: "/settings", marker: "13", label: "Settings" },
    ],
  },
];

export function Sidebar() {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <NavLink className="wordmark" to="/" aria-label="NexusFlow overview">
        <span className="wordmark-mark" aria-hidden="true">NF</span>
        <span>NexusFlow</span>
      </NavLink>
      <nav>
        {sections.map((section) => (
          <section className="nav-section" key={section.label}>
            <h2>{section.label}</h2>
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  isActive ? "nav-item active" : "nav-item"
                }
              >
                <span className="nav-marker" aria-hidden="true">{item.marker}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </section>
        ))}
      </nav>
      <NavLink className="fixture-link" to="/fixture-provenance">
        Fixture provenance
      </NavLink>
    </aside>
  );
}
