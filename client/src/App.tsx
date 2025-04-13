import { Switch, Route } from "wouter";
import { queryClient } from "./lib/queryClient";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { AuthProvider } from "@/hooks/use-auth";
import HomePage from "@/pages/home-page";
import AuthPage from "@/pages/auth-page";
import AdminPage from "@/pages/admin-page";
import AnalyticsPage from "@/pages/admin/analytics-page";
import StationsPage from "@/pages/admin/stations-page";
import UsersPage from "@/pages/admin/users-page";
import SettingsPage from "@/pages/admin/settings-page";
import NotFound from "@/pages/not-found";
import { ProtectedRoute } from "./lib/protected-route";
import { SiteTour } from "@/components/site-tour";
import { FeedbackDialog } from "@/components/feedback-dialog";
import { useAuth } from "@/hooks/use-auth";
import FeedbackPage from "@/pages/admin/feedback-page";
import { SessionReplayPage } from "./pages/session-replay-page";
import { SessionAnalyticsPage } from "./pages/session-analytics-page";
import { SystemHealthPage } from "./pages/system-health-page";
import { TechSpecsPage } from "./pages/tech-specs-page";

function AuthenticatedComponents() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <>
      <SiteTour isAdmin={user.isAdmin} />
      <FeedbackDialog />
    </>
  );
}

function Router() {
  return (
    <Switch>
      <Route path="/auth" component={AuthPage} />
      <ProtectedRoute path="/" component={HomePage} />
      <ProtectedRoute path="/admin" component={AdminPage} />
      <ProtectedRoute path="/admin/stations" component={StationsPage} />
      <ProtectedRoute path="/admin/users" component={UsersPage} />
      <ProtectedRoute path="/admin/analytics" component={AnalyticsPage} />
      <ProtectedRoute path="/admin/feedback" component={FeedbackPage} />
      <ProtectedRoute path="/admin/settings" component={SettingsPage} />
      
      {/* New feature routes */}
      <ProtectedRoute path="/session-replay/:sessionId" component={SessionReplayPage} />
      <ProtectedRoute path="/session-analytics" component={SessionAnalyticsPage} />
      <ProtectedRoute path="/system-health" component={SystemHealthPage} />
      <ProtectedRoute path="/tech-specs" component={TechSpecsPage} />
      
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Router />
        <Toaster />
        <AuthenticatedComponents />
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;