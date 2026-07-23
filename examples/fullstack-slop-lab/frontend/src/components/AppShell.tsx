import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <Sidebar />
      <div className="app-column">
        <TopBar />
        <main className="main-content" id="main-content" tabIndex={-1}>
          <Outlet />
        </main>
        <footer className="product-footer">
          <span>NexusFlow qualification fixture</span>
          <span>All records are synthetic · Last remediated July 2026</span>
        </footer>
      </div>
    </div>
  );
}
