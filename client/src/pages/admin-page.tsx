import { useAuth } from "@/hooks/use-auth";
import { useQuery } from "@tanstack/react-query";
import { Station, SessionLog, User } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useLocation } from "wouter"; // Fixed import from useNavigate
import { Settings, Users, Activity, PlusCircle } from "lucide-react";

export default function AdminPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation(); // Fixed from useNavigate

  const { data: stations } = useQuery<Station[]>({
    queryKey: ["/api/stations"],
  });

  const { data: sessionLogs } = useQuery<SessionLog[]>({
    queryKey: ["/api/admin/session-logs"],
  });

  const { data: users } = useQuery<User[]>({
    queryKey: ["/api/admin/users"],
  });

  if (!user?.isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Card>
          <CardContent className="pt-6">
            <p>You don't have permission to access this page.</p>
            <Button
              className="mt-4"
              onClick={() => setLocation("/")}
            >
              Return to Home
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img 
              src="/Xeryon-logo-v2.png" 
              alt="Xeryon Logo" 
              className="h-8 object-contain"
            />
            <h1 className="text-2xl font-bold">Admin Dashboard</h1>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/stations")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                <span>Stations</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stations?.length || 0}</div>
              <p className="text-sm text-muted-foreground">Active Stations</p>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/users")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                <span>Users</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{users?.length || 0}</div>
              <p className="text-sm text-muted-foreground">Registered Users</p>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/analytics")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                <span>Analytics</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{sessionLogs?.length || 0}</div>
              <p className="text-sm text-muted-foreground">Total Sessions</p>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/stations/new")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <PlusCircle className="h-5 w-5" />
                <span>Add Station</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Create a new demo station</p>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}