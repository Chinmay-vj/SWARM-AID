import { QueryClient, QueryClientProvider, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Skeleton } from "../components/ui/states";
import { AppShell } from "../components/layout/AppShell";
import { MissionLayout } from "../features/missions/MissionLayout";
import { getProvider } from "../services/providers";
import { sessionTokens } from "../services/api/tokens";
import { asApiError } from "../services/api/errors";
import { usePreferences } from "../stores/preferences";
import { useSession } from "../stores/session";
import { useActivity } from "../stores/activity";
import { ErrorBoundary } from "./ErrorBoundary";

const LoginPage = lazy(() => import("../features/authentication/LoginPage"));
const MissionsPage = lazy(() => import("../features/missions/MissionsPage"));
const OverviewPage = lazy(() => import("../features/missions/OverviewPage"));
const MapPage = lazy(() => import("../features/map/MapPage"));
const FleetPage = lazy(() => import("../features/agents/FleetPage"));
const AgentDetailPage = lazy(() => import("../features/agents/AgentDetailPage"));
const ObservationsPage = lazy(() => import("../features/observations/ObservationsPage"));
const EvidencePage = lazy(() => import("../features/evidence/EvidencePage"));
const IncidentsPage = lazy(() => import("../features/incidents/IncidentsPage"));
const IncidentDetailPage = lazy(() => import("../features/incidents/IncidentDetailPage"));
const RecommendationsPage = lazy(() => import("../features/recommendations/RecommendationsPage"));
const RecommendationDetailPage = lazy(() => import("../features/recommendations/RecommendationDetailPage"));
const ReviewPage = lazy(() => import("../features/oversight/ReviewPage"));
const Model2Page = lazy(() => import("../features/model2/Model2Page"));
const CoordinationPage = lazy(() => import("../features/coordination/CoordinationPage"));
const EnvironmentPage = lazy(() => import("../features/environment/EnvironmentPage"));
const CommunicationPage = lazy(() => import("../features/communication/CommunicationPage"));
const EventsPage = lazy(() => import("../features/events/EventsPage"));
const AnalyticsPage = lazy(() => import("../features/analytics/AnalyticsPage"));
const ExperimentsPage = lazy(() => import("../features/analytics/ExperimentsPage"));
const HealthPage = lazy(() => import("../features/system-health/HealthPage"));
const SettingsPage = lazy(() => import("../features/settings/SettingsPage"));
const NotFoundPage = lazy(() => import("../features/common/NotFoundPage"));

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { refetchOnWindowFocus: false, retry: (n, e) => asApiError(e).retryable && n < 2 },
      mutations: { retry: false },
    },
  });
}

/** Applies theme, density, text size and motion preferences to <html>. */
function PreferenceEffects() {
  const { theme, density, largeText, reducedMotion } = usePreferences();
  useEffect(() => {
    const root = document.documentElement;
    const media = window.matchMedia?.("(prefers-color-scheme: light)");
    const apply = () =>
      root.setAttribute("data-theme", theme === "system" ? (media?.matches ? "light" : "dark") : theme);
    apply();
    root.setAttribute("data-density", density);
    root.setAttribute("data-text", largeText ? "large" : "normal");
    root.setAttribute("data-motion", reducedMotion ? "reduced" : "full");
    media?.addEventListener?.("change", apply);
    return () => media?.removeEventListener?.("change", apply);
  }, [theme, density, largeText, reducedMotion]);
  return null;
}

/**
 * Restores a connected session after a page reload (refresh-token in tab session storage) and
 * clears every protected cache when the session ends or expires.
 */
function SessionEffects() {
  const client = useQueryClient();
  const { mode, status, signedIn, signedOut, setRestoring } = useSession();
  useEffect(() => {
    if (status !== "anonymous" || mode !== "connected" || !sessionTokens.refresh()) return;
    setRestoring();
    getProvider("connected")
      .me()
      .then(signedIn)
      .catch(() => signedOut("Your previous session could not be restored. Sign in again."));
    // Only on first load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(
    () =>
      sessionTokens.subscribe((state) => {
        if (state === "expired" && useSession.getState().mode === "connected") {
          client.clear();
          useActivity.getState().clear();
          signedOut("Your session expired. Sign in again to continue.");
        }
      }),
    [client, signedOut],
  );
  return null;
}

function RequireAuth({ children }: { children: ReactNode }) {
  const status = useSession((s) => s.status);
  const location = useLocation();
  if (status === "restoring")
    return (
      <div className="login">
        <Skeleton rows={3} />
      </div>
    );
  if (status !== "authenticated")
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

function Page({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <Suspense fallback={<Skeleton rows={5} />}>{children}</Suspense>
    </ErrorBoundary>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <Page>
            <LoginPage />
          </Page>
        }
      />
      <Route
        element={
          <RequireAuth>
            <AppShell>
              <Outlet />
            </AppShell>
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="/missions" replace />} />
        <Route
          path="missions"
          element={
            <Page>
              <MissionsPage />
            </Page>
          }
        />
        <Route path="missions/:missionId" element={<MissionLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route
            path="overview"
            element={
              <Page>
                <OverviewPage />
              </Page>
            }
          />
          <Route
            path="map"
            element={
              <Page>
                <MapPage />
              </Page>
            }
          />
          <Route
            path="fleet"
            element={
              <Page>
                <FleetPage />
              </Page>
            }
          />
          <Route
            path="fleet/:agentId"
            element={
              <Page>
                <AgentDetailPage />
              </Page>
            }
          />
          <Route
            path="observations"
            element={
              <Page>
                <ObservationsPage />
              </Page>
            }
          />
          <Route
            path="evidence"
            element={
              <Page>
                <EvidencePage />
              </Page>
            }
          />
          <Route
            path="incidents"
            element={
              <Page>
                <IncidentsPage />
              </Page>
            }
          />
          <Route
            path="incidents/:incidentId"
            element={
              <Page>
                <IncidentDetailPage />
              </Page>
            }
          />
          <Route
            path="recommendations"
            element={
              <Page>
                <RecommendationsPage />
              </Page>
            }
          />
          <Route
            path="recommendations/:recId"
            element={
              <Page>
                <RecommendationDetailPage />
              </Page>
            }
          />
          <Route
            path="review"
            element={
              <Page>
                <ReviewPage />
              </Page>
            }
          />
          <Route
            path="model2"
            element={
              <Page>
                <Model2Page />
              </Page>
            }
          />
          <Route
            path="coordination"
            element={
              <Page>
                <CoordinationPage />
              </Page>
            }
          />
          <Route
            path="environment"
            element={
              <Page>
                <EnvironmentPage />
              </Page>
            }
          />
          <Route
            path="communication"
            element={
              <Page>
                <CommunicationPage />
              </Page>
            }
          />
          <Route
            path="events"
            element={
              <Page>
                <EventsPage />
              </Page>
            }
          />
          <Route
            path="analytics"
            element={
              <Page>
                <AnalyticsPage />
              </Page>
            }
          />
          <Route
            path="*"
            element={
              <Page>
                <NotFoundPage />
              </Page>
            }
          />
        </Route>
        <Route
          path="experiments"
          element={
            <Page>
              <ExperimentsPage />
            </Page>
          }
        />
        <Route
          path="system"
          element={
            <Page>
              <HealthPage />
            </Page>
          }
        />
        <Route
          path="settings"
          element={
            <Page>
              <SettingsPage />
            </Page>
          }
        />
        <Route
          path="*"
          element={
            <Page>
              <NotFoundPage />
            </Page>
          }
        />
      </Route>
    </Routes>
  );
}

export function Providers({ children, client }: { children: ReactNode; client?: QueryClient }) {
  return (
    <QueryClientProvider client={client ?? defaultClient}>
      <PreferenceEffects />
      <SessionEffects />
      {children}
    </QueryClientProvider>
  );
}

const defaultClient = createQueryClient();

export default function App() {
  return (
    <Providers>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </Providers>
  );
}
