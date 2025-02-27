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
import NotFound from "@/pages/not-found";
import { ProtectedRoute } from "./lib/protected-route";
import { SiteTour } from "@/components/site-tour";
import { FeedbackDialog } from "@/components/feedback-dialog";
import { useAuth } from "@/hooks/use-auth";

function Router() {
  const { user } = useAuth();

  return (
    <>
      <Switch>
        <ProtectedRoute path="/" component={HomePage} />
        <ProtectedRoute path="/admin" component={AdminPage} />
        <ProtectedRoute path="/admin/analytics" component={AnalyticsPage} />
        <ProtectedRoute path="/admin/stations" component={StationsPage} />
        <ProtectedRoute path="/admin/users" component={UsersPage} />
        <Route path="/auth" component={AuthPage} />
        <Route component={NotFound} />
      </Switch>
      <SiteTour isAdmin={user?.isAdmin} />
      <FeedbackDialog />
    </>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <Router />
        <Toaster />
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;