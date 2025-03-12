import { useQuery } from "@tanstack/react-query";
import { SessionLog, User, Station } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useLocation } from "wouter";
import { ArrowLeft, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts';

export default function AnalyticsPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation();

  const { data: sessionLogs, isLoading: isLoadingLogs } = useQuery<SessionLog[]>({
    queryKey: ["/api/admin/session-logs"],
  });

  const { data: users, isLoading: isLoadingUsers } = useQuery<User[]>({
    queryKey: ["/api/admin/users"],
  });

  const { data: stations, isLoading: isLoadingStations } = useQuery<Station[]>({
    queryKey: ["/api/stations"],
  });

  const isLoading = isLoadingLogs || isLoadingUsers || isLoadingStations;

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

  // Process session logs for analytics
  const stationUsage = stations?.map(station => {
    const stationSessions = sessionLogs?.filter(log => log.stationId === station.id) || [];
    const totalCommands = stationSessions.reduce((sum, log) => sum + log.commandCount, 0);
    const totalDuration = stationSessions.reduce((sum, log) => {
      if (!log.endTime) return sum;
      return sum + (new Date(log.endTime).getTime() - new Date(log.startTime).getTime());
    }, 0);

    return {
      name: station.name,
      sessions: stationSessions.length,
      commands: totalCommands,
      duration: Math.round(totalDuration / (1000 * 60)), // Convert to minutes
    };
  }) || [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              className="hover:bg-accent hover:text-accent-foreground transition-colors"
              onClick={() => setLocation("/admin")}
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-2xl font-bold">Usage Analytics</h1>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          <Card className="hover:bg-accent/5 transition-colors">
            <CardHeader>
              <CardTitle>Total Sessions</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-primary">{sessionLogs?.length || 0}</div>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors">
            <CardHeader>
              <CardTitle>Active Users</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-primary">
                {new Set(sessionLogs?.map(log => log.userId)).size || 0}
              </div>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors">
            <CardHeader>
              <CardTitle>Total Commands</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-primary">
                {sessionLogs?.reduce((sum, log) => sum + log.commandCount, 0) || 0}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="hover:bg-accent/5 transition-colors">
            <CardHeader>
              <CardTitle>Station Usage</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stationUsage}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-50" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'hsl(var(--background))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '0.5rem',
                      }}
                    />
                    <Bar 
                      dataKey="sessions" 
                      fill="hsl(var(--primary))" 
                      name="Sessions"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors">
            <CardHeader>
              <CardTitle>Command Activity</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stationUsage}>
                    <CartesianGrid strokeDasharray="3 3" className="opacity-50" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: 'hsl(var(--background))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '0.5rem',
                      }}
                    />
                    <Bar 
                      dataKey="commands" 
                      fill="hsl(var(--primary))" 
                      name="Commands"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}