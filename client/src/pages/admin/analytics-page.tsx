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
    const totalCommands = stationSessions.reduce((sum, log) => sum + (log.commandCount || 0), 0);
    const totalDuration = stationSessions.reduce((sum, log) => {
      if (!log.endTime) return sum;
      return sum + (new Date(log.endTime).getTime() - new Date(log.startTime).getTime());
    }, 0);

    return {
      id: station.id,
      name: station.name,
      sessions: stationSessions.length,
      commands: totalCommands,
      duration: Math.round(totalDuration / (1000 * 60)), // Convert to minutes
    };
  }) || [];
  
  // Process user data for analytics
  const userActivity = users?.map(user => {
    const userSessions = sessionLogs?.filter(log => log.userId === user.id) || [];
    const totalCommands = userSessions.reduce((sum, log) => sum + (log.commandCount || 0), 0);
    const totalDuration = userSessions.reduce((sum, log) => {
      if (!log.endTime) return sum;
      return sum + (new Date(log.endTime).getTime() - new Date(log.startTime).getTime());
    }, 0);
    
    return {
      id: user.id,
      username: user.username,
      isAdmin: user.isAdmin,
      sessions: userSessions.length,
      commands: totalCommands,
      duration: Math.round(totalDuration / (1000 * 60)), // Convert to minutes
    };
  }) || [];
  
  // Calculate session duration distribution
  const sessionDurations = sessionLogs?.map(log => {
    if (!log.endTime) return 0;
    return Math.round((new Date(log.endTime).getTime() - new Date(log.startTime).getTime()) / (1000 * 60));
  }).filter(duration => duration > 0) || [];
  
  const durationBuckets = {
    '< 5 min': 0,
    '5-15 min': 0,
    '15-30 min': 0,
    '30-60 min': 0,
    '> 60 min': 0
  };
  
  sessionDurations.forEach(duration => {
    if (duration < 5) durationBuckets['< 5 min']++;
    else if (duration < 15) durationBuckets['5-15 min']++;
    else if (duration < 30) durationBuckets['15-30 min']++;
    else if (duration < 60) durationBuckets['30-60 min']++;
    else durationBuckets['> 60 min']++;
  });
  
  const durationData = Object.entries(durationBuckets).map(([range, count]) => ({
    range,
    count
  }));

  // Create hourly activity distribution
  const hourlyActivity = Array(24).fill(0);
  sessionLogs?.forEach(log => {
    const hour = new Date(log.startTime).getHours();
    hourlyActivity[hour]++;
  });
  
  const hourlyData = hourlyActivity.map((count, hour) => ({
    hour: `${hour}:00`,
    sessions: count
  }));

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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
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
                {sessionLogs?.reduce((sum, log) => sum + (log.commandCount || 0), 0) || 0}
              </div>
            </CardContent>
          </Card>
          
          <Card className="hover:bg-accent/5 transition-colors">
            <CardHeader>
              <CardTitle>Avg. Session Duration</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-4xl font-bold text-primary">
                {sessionDurations.length ? Math.round(sessionDurations.reduce((sum, duration) => sum + duration, 0) / sessionDurations.length) : 0} min
              </div>
            </CardContent>
          </Card>
        </div>
        
        {/* Station Usage Chart */}
        <div className="grid grid-cols-1 gap-6 mb-8">
          <Card>
            <CardHeader>
              <CardTitle>Station Usage</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              {stationUsage.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stationUsage}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis yAxisId="left" orientation="left" stroke="#8884d8" />
                    <YAxis yAxisId="right" orientation="right" stroke="#82ca9d" />
                    <Tooltip />
                    <Bar yAxisId="left" dataKey="sessions" name="Sessions" fill="#8884d8" />
                    <Bar yAxisId="right" dataKey="commands" name="Commands" fill="#82ca9d" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-muted-foreground">No station usage data available</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        
        {/* User Activity and Session Duration Charts */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <Card>
            <CardHeader>
              <CardTitle>Top User Activity</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              {userActivity.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={userActivity.sort((a, b) => b.sessions - a.sessions).slice(0, 5)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="username" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="sessions" name="Sessions" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-muted-foreground">No user activity data available</p>
                </div>
              )}
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader>
              <CardTitle>Session Duration Distribution</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              {durationData.some(item => item.count > 0) ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={durationData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="range" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="count" name="Sessions" fill="#82ca9d" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-muted-foreground">No session duration data available</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        
        {/* Hourly Activity Chart */}
        <div className="grid grid-cols-1 gap-6 mb-8">
          <Card>
            <CardHeader>
              <CardTitle>Hourly Activity Distribution</CardTitle>
            </CardHeader>
            <CardContent className="h-80">
              {hourlyData.some(item => item.sessions > 0) ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hourlyData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="hour" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="sessions" name="Sessions" fill="#8884d8" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full">
                  <p className="text-muted-foreground">No hourly activity data available</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        
        {/* Raw Data Section */}
        <div className="space-y-6">
          <h2 className="text-2xl font-bold">Raw Data</h2>
          
          <div className="space-y-4">
            <h3 className="text-xl font-semibold">Session Logs ({sessionLogs?.length || 0})</h3>
            <div className="border rounded-lg overflow-auto max-h-96">
              <table className="min-w-full divide-y divide-border">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">ID</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Station</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">User</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Start Time</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">End Time</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Commands</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Duration</th>
                  </tr>
                </thead>
                <tbody className="bg-card divide-y divide-border">
                  {sessionLogs?.map(log => {
                    const station = stations?.find(s => s.id === log.stationId);
                    const user = users?.find(u => u.id === log.userId);
                    const duration = log.endTime 
                      ? Math.round((new Date(log.endTime).getTime() - new Date(log.startTime).getTime()) / (1000 * 60))
                      : "Active";
                    
                    return (
                      <tr key={log.id}>
                        <td className="px-4 py-2 whitespace-nowrap text-sm">{log.id}</td>
                        <td className="px-4 py-2 whitespace-nowrap text-sm">{station?.name || log.stationId}</td>
                        <td className="px-4 py-2 whitespace-nowrap text-sm">{user?.username || log.userId}</td>
                        <td className="px-4 py-2 whitespace-nowrap text-sm">{new Date(log.startTime).toLocaleString()}</td>
                        <td className="px-4 py-2 whitespace-nowrap text-sm">{log.endTime ? new Date(log.endTime).toLocaleString() : "Active"}</td>
                        <td className="px-4 py-2 whitespace-nowrap text-sm">{log.commandCount || 0}</td>
                        <td className="px-4 py-2 whitespace-nowrap text-sm">{typeof duration === "number" ? `${duration} min` : duration}</td>
                      </tr>
                    )
                  })}
                  {!sessionLogs?.length && (
                    <tr>
                      <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground">No session logs available</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
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