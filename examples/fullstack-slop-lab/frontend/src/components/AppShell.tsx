import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell() {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="app-column">
        <TopBar />
        <main className="main-content">
          <Outlet />
        </main>
        <footer className="ai-footer">
          <div>
            <strong>NexusFlow AI</strong>
            <p>Empowering modern teams to unlock limitless possibilities.</p>
          </div>
          <div>
            <b>Product</b>
            <a href="#">Features</a>
            <a href="#">Pricing</a>
            <a href="#">Integrations</a>
          </div>
          <div>
            <b>Company</b>
            <a href="#">About</a>
            <a href="#">Blog</a>
            <a href="#">Careers</a>
          </div>
          <div>
            <b>Resources</b>
            <a href="#">Docs</a>
            <a href="#">Community</a>
            <a href="#">Support</a>
          </div>
        </footer>
      </div>
    </div>
  );
}

