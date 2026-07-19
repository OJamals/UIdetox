import { useState } from "react";

export function TopBar() {
  const [query, setQuery] = useState("");

  return (
    <header className="topbar">
      <div className="search-box">
        <span>🔍</span>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search anything with AI..."
        />
        <kbd>⌘ K</kbd>
      </div>
      <div className="top-actions">
        <button className="icon-button">🔔</button>
        <button className="avatar-button">
          <span>JD</span>
          <small>Jane Doe</small>
        </button>
      </div>
    </header>
  );
}

