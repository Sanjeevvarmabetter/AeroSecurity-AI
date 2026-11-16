import { Suspense, lazy } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "./layouts/AppLayout";
import { OverviewPage } from "./pages/OverviewPage";
import { AssistantPage } from "./pages/AssistantPage";
import { AIConfigPage } from "./pages/AIConfigPage";
import { AnomalyCenterPage } from "./pages/AnomalyCenterPage";
import { AnomalyDetailPage } from "./pages/AnomalyDetailPage";
import { DataSourcesPage } from "./pages/DataSourcesPage";
import { EmergencyPage } from "./pages/EmergencyPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { ReportsPage } from "./pages/ReportsPage";
import { ThreatIntelPage } from "./pages/ThreatIntelPage";
import { SystemHealthPage } from "./pages/SystemHealthPage";
import { FlightAnalyticsPage } from "./pages/FlightAnalyticsPage";
import { TrajectoryAnalysisPage } from "./pages/TrajectoryAnalysisPage";
import { AirportIntelligencePage } from "./pages/AirportIntelligencePage";
import { DetectionRulesPage } from "./pages/DetectionRulesPage";

const AircraftPage = lazy(() => import("./pages/AircraftPage").then((m) => ({ default: m.AircraftPage })));
const RadarPage = lazy(() => import("./pages/RadarPage").then((m) => ({ default: m.RadarPage })));

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } });

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            {/* Surveillance & Radar */}
            <Route index element={<OverviewPage />} />
            <Route path="radar" element={<Suspense fallback={<p className="text-muted p-6">Loading radar viewport...</p>}><RadarPage /></Suspense>} />
            <Route path="aircraft/:icao24?" element={<Suspense fallback={<p className="text-muted p-6">Loading aircraft intelligence...</p>}><AircraftPage /></Suspense>} />

            {/* Analytics & Dynamics */}
            <Route path="analytics" element={<FlightAnalyticsPage />} />
            <Route path="trajectories" element={<TrajectoryAnalysisPage />} />
            <Route path="airports" element={<AirportIntelligencePage />} />

            {/* Security Operations */}
            <Route path="anomalies" element={<AnomalyCenterPage />} />
            <Route path="anomalies/:id" element={<AnomalyDetailPage />} />
            <Route path="emergencies" element={<EmergencyPage />} />
            <Route path="investigations" element={<InvestigationsPage />} />
            <Route path="investigations/:id" element={<InvestigationDetailPage />} />
            <Route path="rules" element={<DetectionRulesPage />} />

            {/* Intelligence & AI */}
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="threat-intel" element={<ThreatIntelPage />} />
            <Route path="reports/:id?" element={<ReportsPage />} />

            {/* System Infrastructure */}
            <Route path="ai-config" element={<AIConfigPage />} />
            <Route path="data-sources" element={<DataSourcesPage />} />
            <Route path="system-health" element={<SystemHealthPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
