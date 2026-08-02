import { Route, Routes } from "react-router";
import { AppShell } from "./components/AppShell";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { AutomationsPage } from "./pages/AutomationsPage";
import { BillingPage } from "./pages/BillingPage";
import {
  AuditLogPage,
  FeatureFlagsPage,
  MarketplacePage,
  ServiceHealthPage,
  WorkQueuePage,
} from "./pages/ControlPlanePages";
import { CustomersPage } from "./pages/CustomersPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DataHubPage } from "./pages/DataHubPage";
import { ExperimentsPage } from "./pages/ExperimentsPage";
import { FixtureProvenancePage } from "./pages/FixtureProvenancePage";
import {
  CatalogPage,
  InventoryPage,
  OrderDetailPage,
  OrdersPage,
  ShipmentsPage,
} from "./pages/FulfillmentPages";
import {
  CampaignsPage,
  ContentLibraryPage,
  SegmentsPage,
  SurveysPage,
} from "./pages/GrowthPages";
import { InboxPage } from "./pages/InboxPage";
import { JourneysPage } from "./pages/JourneysPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProjectDetailPage } from "./pages/ProjectDetailPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import {
  ForecastPage,
  OpportunityDetailPage,
  PipelinePage,
} from "./pages/RevenuePages";
import { SettingsPage } from "./pages/SettingsPage";
import {
  ServiceLevelsPage,
  SupportCasePage,
  SupportPage,
} from "./pages/SupportPages";
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
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/pipeline/:opportunityId" element={<OpportunityDetailPage />} />
        <Route path="/forecast" element={<ForecastPage />} />
        <Route path="/support" element={<SupportPage />} />
        <Route path="/support/:caseId" element={<SupportCasePage />} />
        <Route path="/service-levels" element={<ServiceLevelsPage />} />
        <Route path="/catalog" element={<CatalogPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        <Route path="/inventory" element={<InventoryPage />} />
        <Route path="/shipments" element={<ShipmentsPage />} />
        <Route path="/campaigns" element={<CampaignsPage />} />
        <Route path="/segments" element={<SegmentsPage />} />
        <Route path="/content-library" element={<ContentLibraryPage />} />
        <Route path="/surveys" element={<SurveysPage />} />
        <Route path="/audit-log" element={<AuditLogPage />} />
        <Route path="/feature-flags" element={<FeatureFlagsPage />} />
        <Route path="/service-health" element={<ServiceHealthPage />} />
        <Route path="/marketplace" element={<MarketplacePage />} />
        <Route path="/work-queue" element={<WorkQueuePage />} />
        <Route path="/team" element={<TeamPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/fixture-provenance" element={<FixtureProvenancePage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
