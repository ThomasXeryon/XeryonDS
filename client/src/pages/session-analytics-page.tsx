import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, 
  ResponsiveContainer, PieChart, Pie, Cell 
} from 'recharts';
import { 
  Clock, Activity, CalendarRange, Users, RefreshCw, 
  Command, ChevronRight, TrendingUp, TrendingDown 
} from "lucide-react";

interface SessionAnalytics {
  totalSessions: number;
  averageDuration: number;
  commandFrequency: Record<string, number>;
  activeStations: Array<{ stationId: number; sessionCount: number }>;
}

export function SessionAnalyticsPage() {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  
  // Fetch session analytics data
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['/api/session-analytics', startDate, endDate],
    queryFn: async () => {
      let url = '/api/session-analytics';
      const params = new URLSearchParams();
      
      if (startDate) {
        params.append('startDate', startDate);
      }
      if (endDate) {
        params.append('endDate', endDate);
      }
      
      if (params.toString()) {
        url += `?${params.toString()}`;
      }
      
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Failed to fetch session analytics data');
      }
      return response.json() as Promise<SessionAnalytics>;
    }
  });
  
  // Apply date filter
  const applyFilter = () => {
    refetch();
  };
  
  // Reset date filter
  const resetFilter = () => {
    setStartDate('');
    setEndDate('');
    refetch();
  };
  
  // Format duration for display
  const formatDuration = (milliseconds: number) => {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${seconds}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${seconds}s`;
    } else {
      return `${seconds}s`;
    }
  };
  
  if (isLoading) {
    return <div className="flex justify-center items-center min-h-screen">Loading analytics data...</div>;
  }
  
  if (error || !data) {
    return (
      <div className="p-4">
        <Card className="max-w-4xl mx-auto">
          <CardHeader>
            <CardTitle className="text-red-500">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p>Failed to load session analytics data. Please try again.</p>
            <Button variant="default" className="mt-4" onClick={() => refetch()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  
  // Prepare data for charts
  const commandChartData = Object.entries(data.commandFrequency).map(([command, count]) => ({
    name: command,
    value: count
  }));
  
  const stationChartData = data.activeStations.map(station => ({
    name: `Station ${station.stationId}`,
    value: station.sessionCount
  }));
  
  // Pie chart colors
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d'];
  
  return (
    <div className="p-4">
      <Card className="max-w-5xl mx-auto">
        <CardHeader>
          <CardTitle>Session Analytics</CardTitle>
          <CardDescription>
            View and analyze usage patterns and session statistics
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row gap-4 mb-6">
            <div className="space-y-2 w-full md:w-1/2">
              <Label htmlFor="startDate">Start Date</Label>
              <Input 
                type="date" 
                id="startDate" 
                value={startDate} 
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>
            <div className="space-y-2 w-full md:w-1/2">
              <Label htmlFor="endDate">End Date</Label>
              <Input 
                type="date" 
                id="endDate" 
                value={endDate} 
                onChange={(e) => setEndDate(e.target.value)}
              />
            </div>
          </div>
          
          <div className="flex gap-2 mb-8">
            <Button variant="default" onClick={applyFilter}>
              Apply Filter
            </Button>
            <Button variant="outline" onClick={resetFilter}>
              Reset
            </Button>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center">
                  <Activity className="h-4 w-4 mr-2" />
                  Total Sessions
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{data.totalSessions}</div>
                <p className="text-sm text-muted-foreground">
                  {startDate && endDate 
                    ? `Between ${new Date(startDate).toLocaleDateString()} and ${new Date(endDate).toLocaleDateString()}`
                    : 'All time'
                  }
                </p>
              </CardContent>
            </Card>
            
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center">
                  <Clock className="h-4 w-4 mr-2" />
                  Average Session Duration
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{formatDuration(data.averageDuration)}</div>
                <p className="text-sm text-muted-foreground">
                  Across {data.totalSessions} sessions
                </p>
              </CardContent>
            </Card>
          </div>
          
          <Tabs defaultValue="commands">
            <TabsList className="mb-4">
              <TabsTrigger value="commands">
                <Command className="h-4 w-4 mr-2" />
                Command Usage
              </TabsTrigger>
              <TabsTrigger value="stations">
                <TrendingUp className="h-4 w-4 mr-2" />
                Station Activity
              </TabsTrigger>
            </TabsList>
            
            <TabsContent value="commands">
              <div className="h-[400px]">
                {commandChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="h-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={commandChartData}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            <Bar dataKey="value" name="Usage Count" fill="#3b82f6" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="h-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={commandChartData}
                              cx="50%"
                              cy="50%"
                              labelLine={false}
                              label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                              outerRadius={80}
                              fill="#8884d8"
                              dataKey="value"
                            >
                              {commandChartData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(value) => [`${value} executions`, 'Usage']} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex justify-center items-center h-full">
                    <p>No command data available for the selected period</p>
                  </div>
                )}
              </div>
              
              <div className="mt-4">
                <h3 className="text-lg font-semibold mb-2">Command Usage Breakdown</h3>
                <div className="space-y-1">
                  {Object.entries(data.commandFrequency)
                    .sort((a, b) => b[1] - a[1])
                    .map(([command, count]) => (
                      <div key={command} className="flex justify-between items-center p-2 hover:bg-muted rounded-md">
                        <div className="flex items-center">
                          <ChevronRight className="h-4 w-4 mr-2" />
                          <span className="font-medium">{command}</span>
                        </div>
                        <div>{count} executions</div>
                      </div>
                  ))}
                </div>
              </div>
            </TabsContent>
            
            <TabsContent value="stations">
              <div className="h-[400px]">
                {stationChartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="h-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={stationChartData}>
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis dataKey="name" />
                            <YAxis />
                            <Tooltip />
                            <Legend />
                            <Bar dataKey="value" name="Session Count" fill="#10b981" />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="h-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={stationChartData}
                              cx="50%"
                              cy="50%"
                              labelLine={false}
                              label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                              outerRadius={80}
                              fill="#8884d8"
                              dataKey="value"
                            >
                              {stationChartData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                              ))}
                            </Pie>
                            <Tooltip formatter={(value) => [`${value} sessions`, 'Count']} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex justify-center items-center h-full">
                    <p>No station data available for the selected period</p>
                  </div>
                )}
              </div>
              
              <div className="mt-4">
                <h3 className="text-lg font-semibold mb-2">Station Usage Breakdown</h3>
                <div className="space-y-1">
                  {data.activeStations
                    .sort((a, b) => b.sessionCount - a.sessionCount)
                    .map((station) => (
                      <div key={station.stationId} className="flex justify-between items-center p-2 hover:bg-muted rounded-md">
                        <div className="flex items-center">
                          <ChevronRight className="h-4 w-4 mr-2" />
                          <span className="font-medium">Station {station.stationId}</span>
                        </div>
                        <div>{station.sessionCount} sessions</div>
                      </div>
                  ))}
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}