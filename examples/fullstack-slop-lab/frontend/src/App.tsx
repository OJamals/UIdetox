import { Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AutomationsPage } from "./pages/AutomationsPage";
import { BillingPage } from "./pages/BillingPage";
import { CustomersPage } from "./pages/CustomersPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DataHubPage } from "./pages/DataHubPage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { InboxPage } from "./pages/InboxPage";
import { JourneysPage } from "./pages/JourneysPage";
import { FixtureProvenancePage } from "./pages/FixtureProvenancePage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TeamPage } from "./pages/TeamPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/automations" element={<AutomationsPage />} />
        <Route path="/inbox" element={<InboxPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/customers" element={<CustomersPage />} />
        <Route path="/data-hub" element={<DataHubPage />} />
        <Route path="/approvals" element={<ApprovalsPage />} />
        <Route path="/journeys" element={<JourneysPage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/fixture-provenance" element={<FixtureProvenancePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
