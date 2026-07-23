import { FormEvent, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export function TopBar() {
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [showProfile, setShowProfile] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const routeQuery = new URLSearchParams(location.search).get("search") || "";
    setQuery(location.pathname === "/projects" ? routeQuery : "");
  }, [location.pathname, location.search]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = query.trim();
    navigate(value ? `/projects?search=${encodeURIComponent(value)}` : "/projects");
  }

  return (
    <header className="topbar">
      <form className="global-search" role="search" onSubmit={search}>
        <label htmlFor="global-search">Search projects</label>
        <input
          id="global-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Project name or description"
        />
        <button type="submit">Search</button>
      </form>
      <div className="top-actions">
        <button
          type="button"
          className="quiet-button"
          onClick={() => setNotice("You have three unread workspace updates.")}
        >
          Updates <span aria-hidden="true">3</span>
        </button>
        <button
          type="button"
          className="profile-button"
          aria-expanded={showProfile}
          onClick={() => setShowProfile((current) => !current)}
        >
          <span aria-hidden="true">NO</span>
          Northstar Operator
        </button>
        {showProfile && (
          <div className="profile-menu">
            <strong>Northstar Operator</strong>
            <span>Workspace owner</span>
            <button type="button" onClick={() => navigate("/settings")}>Open settings</button>
          </div>
        )}
      </div>
      <p className="sr-only" aria-live="polite">{notice}</p>
    </header>
  );
}
