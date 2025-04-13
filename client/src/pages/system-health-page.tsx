import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, 
  ResponsiveContainer, AreaChart, Area 
} from 'recharts';
import { 
  Activity, Server, Cpu, HardDrive, Clock, Wifi, 
  AlertTriangle, CheckCircle2, BarChart 
} from "lucide-react";

interface SystemHealthStatus {
  id: number;
  stationId: number;
  status: string;
  connectionLatency?: number;
  cpuUsage?: number;
  memoryUsage?: number;
  uptimeSeconds?: number;
  details?: any;
  timestamp: string;
}

export function SystemHealthPage() {
  const [selectedStation, setSelectedStation] = useState<number | null>(null);
  const [refreshInterval, setRefreshInterval] = useState(30000); // 30 seconds
  
  // Fetch stations to populate dropdown
  const { data: stations, isLoading: stationsLoading } = useQuery({
    queryKey: ['/api/stations'],
    queryFn: async () => {
      const response = await fetch('/api/stations');
      if (!response.ok) {
        throw new Error('Failed to fetch stations');
      }
      return response.json();
    }
  });
  
  // Set the first station as default when data is loaded
  useEffect(() => {
    if (stations && stations.length > 0 && !selectedStation) {
      setSelectedStation(stations[0].id);
    }
  }, [stations, selectedStation]);
  
  // Fetch health data for selected station
  const { 
    data: healthData, 
    isLoading: healthLoading, 
    error: healthError,
    refetch: refetchHealth
  } = useQuery({
    queryKey: ['/api/system-health', selectedStation],
    queryFn: async () => {
      if (!selectedStation) return null;
      
      const response = await fetch(`/api/system-health/${selectedStation}?limit=100`);
      if (!response.ok) {
        throw new Error('Failed to fetch system health data');
      }
      return response.json() as Promise<SystemHealthStatus[]>;
    },
    enabled: !!selectedStation,
    refetchInterval: refreshInterval
  });
  
  // Fetch latest health status
  const { 
    data: latestHealth, 
    isLoading: latestHealthLoading,
    refetch: refetchLatest
  } = useQuery({
    queryKey: ['/api/system-health/latest', selectedStation],
    queryFn: async () => {
      if (!selectedStation) return null;
      
      const response = await fetch(`/api/system-health/${selectedStation}/latest`);
      if (!response.ok) {
        if (response.status === 404) {
          return null; // No health data yet
        }
        throw new Error('Failed to fetch latest system health data');
      }
      return response.json() as Promise<SystemHealthStatus>;
    },
    enabled: !!selectedStation,
    refetchInterval: refreshInterval
  });
  
  // Manual refresh
  const handleRefresh = () => {
    refetchHealth();
    refetchLatest();
  };
  
  // Format date for display
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };
  
  // Format uptime for display
  const formatUptime = (seconds?: number) => {
    if (!seconds) return 'N/A';
    
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    
    if (days > 0) {
      return `${days}d ${hours}h ${minutes}m`;
    } else if (hours > 0) {
      return `${hours}h ${minutes}m ${remainingSeconds}s`;
    } else if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    } else {
      return `${remainingSeconds}s`;
    }
  };
  
  // Get status color
  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'online':
      case 'ok':
      case 'good':
        return 'text-green-500';
      case 'warning':
      case 'degraded':
        return 'text-yellow-500';
      case 'error':
      case 'offline':
      case 'critical':
        return 'text-red-500';
      default:
        return 'text-gray-500';
    }
  };
  
  // Get background color based on status
  const getStatusBgColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'online':
      case 'ok':
      case 'good':
        return 'bg-green-100 dark:bg-green-900/20';
      case 'warning':
      case 'degraded':
        return 'bg-yellow-100 dark:bg-yellow-900/20';
      case 'error':
      case 'offline':
      case 'critical':
        return 'bg-red-100 dark:bg-red-900/20';
      default:
        return 'bg-gray-100 dark:bg-gray-800';
    }
  };
  
  // Get icon based on status
  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'online':
      case 'ok':
      case 'good':
        return <CheckCircle2 className="h-5 w-5 text-green-500" />;
      case 'warning':
      case 'degraded':
        return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
      case 'error':
      case 'offline':
      case 'critical':
        return <AlertTriangle className="h-5 w-5 text-red-500" />;
      default:
        return <Activity className="h-5 w-5 text-gray-500" />;
    }
  };
  
  if (stationsLoading) {
    return <div className="flex justify-center items-center min-h-screen">Loading stations...</div>;
  }
  
  if (!stations || stations.length === 0) {
    return (
      <div className="p-4">
        <Card className="max-w-4xl mx-auto">
          <CardHeader>
            <CardTitle>System Health Dashboard</CardTitle>
          </CardHeader>
          <CardContent>
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>No Stations Available</AlertTitle>
              <AlertDescription>
                No stations are currently configured in the system. Please add a station first.
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      </div>
    );
  }
  
  // Prepare data for charts
  const prepareChartData = () => {
    if (!healthData || healthData.length === 0) return [];
    
    return healthData
      .slice()
      .reverse()
      .map(item => ({
        timestamp: new Date(item.timestamp).getTime(),
        formattedTime: new Date(item.timestamp).toLocaleTimeString(),
        connectionLatency: item.connectionLatency || 0,
        cpuUsage: item.cpuUsage || 0,
        memoryUsage: item.memoryUsage || 0,
        status: item.status
      }));
  };
  
  const chartData = prepareChartData();
  
  return (
    <div className="p-4">
      <Card className="max-w-5xl mx-auto">
        <CardHeader>
          <CardTitle>System Health Dashboard</CardTitle>
          <CardDescription>
            Monitor the status and performance of your stations in real-time
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row justify-between gap-4 mb-6">
            <div className="space-y-2 w-full md:w-1/3">
              <Label htmlFor="station-select">Select Station</Label>
              <Select 
                value={selectedStation?.toString() || ''} 
                onValueChange={(value) => setSelectedStation(parseInt(value))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a station" />
                </SelectTrigger>
                <SelectContent>
                  {stations.map((station: any) => (
                    <SelectItem key={station.id} value={station.id.toString()}>
                      {station.name} ({station.rpiId})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="space-y-2 w-full md:w-1/3">
              <Label htmlFor="refresh-interval">Refresh Interval</Label>
              <Select 
                value={refreshInterval.toString()} 
                onValueChange={(value) => setRefreshInterval(parseInt(value))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select refresh interval" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5000">5 seconds</SelectItem>
                  <SelectItem value="15000">15 seconds</SelectItem>
                  <SelectItem value="30000">30 seconds</SelectItem>
                  <SelectItem value="60000">1 minute</SelectItem>
                  <SelectItem value="300000">5 minutes</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            <div className="flex items-end">
              <Button variant="default" onClick={handleRefresh} className="w-full md:w-auto">
                Refresh Now
              </Button>
            </div>
          </div>
          
          {healthLoading || latestHealthLoading ? (
            <div className="h-48 flex justify-center items-center">
              <p>Loading health data...</p>
            </div>
          ) : healthError ? (
            <Alert variant="destructive" className="mb-6">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>
                Failed to load system health data. Please try refreshing.
              </AlertDescription>
            </Alert>
          ) : (
            <>
              {/* Current Status Overview */}
              <div className={`p-4 rounded-lg mb-6 ${latestHealth ? getStatusBgColor(latestHealth.status) : 'bg-gray-100 dark:bg-gray-800'}`}>
                <div className="flex items-center gap-3 mb-2">
                  {latestHealth ? getStatusIcon(latestHealth.status) : <Activity className="h-5 w-5" />}
                  <h3 className="text-lg font-semibold">
                    Current Status: 
                    <span className={`ml-2 ${latestHealth ? getStatusColor(latestHealth.status) : ''}`}>
                      {latestHealth ? latestHealth.status.toUpperCase() : 'Unknown'}
                    </span>
                  </h3>
                </div>
                
                {latestHealth && (
                  <div className="text-sm text-muted-foreground">
                    Last updated: {formatDate(latestHealth.timestamp)}
                  </div>
                )}
              </div>
              
              {/* Current Metrics */}
              {latestHealth && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base flex items-center">
                        <Wifi className="h-4 w-4 mr-2" />
                        Connection Latency
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {latestHealth.connectionLatency !== undefined
                          ? `${latestHealth.connectionLatency.toFixed(2)} ms`
                          : 'N/A'}
                      </div>
                      <Progress 
                        value={latestHealth.connectionLatency !== undefined 
                          ? Math.min(100, (latestHealth.connectionLatency / 200) * 100) // Assuming 200ms is "100%"
                          : 0
                        } 
                        className="h-2 mt-2"
                      />
                    </CardContent>
                  </Card>
                  
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base flex items-center">
                        <Cpu className="h-4 w-4 mr-2" />
                        CPU Usage
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {latestHealth.cpuUsage !== undefined
                          ? `${latestHealth.cpuUsage.toFixed(1)}%`
                          : 'N/A'}
                      </div>
                      <Progress 
                        value={latestHealth.cpuUsage} 
                        className="h-2 mt-2"
                      />
                    </CardContent>
                  </Card>
                  
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base flex items-center">
                        <Memory className="h-4 w-4 mr-2" />
                        Memory Usage
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {latestHealth.memoryUsage !== undefined
                          ? `${latestHealth.memoryUsage.toFixed(1)}%`
                          : 'N/A'}
                      </div>
                      <Progress 
                        value={latestHealth.memoryUsage} 
                        className="h-2 mt-2"
                      />
                    </CardContent>
                  </Card>
                </div>
              )}
              
              {/* Additional Info */}
              {latestHealth && (
                <div className="mb-6">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-base flex items-center">
                        <Server className="h-4 w-4 mr-2" />
                        System Information
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <p className="text-sm font-medium text-muted-foreground mb-1">Uptime</p>
                          <p className="font-medium">{formatUptime(latestHealth.uptimeSeconds)}</p>
                        </div>
                        
                        <div>
                          <p className="text-sm font-medium text-muted-foreground mb-1">Status Updated</p>
                          <p className="font-medium">{formatDate(latestHealth.timestamp)}</p>
                        </div>
                        
                        {latestHealth.details && Object.entries(latestHealth.details).map(([key, value]) => (
                          <div key={key}>
                            <p className="text-sm font-medium text-muted-foreground mb-1">
                              {key.charAt(0).toUpperCase() + key.slice(1).replace(/([A-Z])/g, ' $1')}
                            </p>
                            <p className="font-medium">{String(value)}</p>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}
              
              {/* Historical Data Charts */}
              {chartData.length > 0 ? (
                <Tabs defaultValue="latency">
                  <TabsList className="mb-4">
                    <TabsTrigger value="latency">
                      <Wifi className="h-4 w-4 mr-2" />
                      Connection Latency
                    </TabsTrigger>
                    <TabsTrigger value="usage">
                      <BarChart className="h-4 w-4 mr-2" />
                      Resource Usage
                    </TabsTrigger>
                  </TabsList>
                  
                  <TabsContent value="latency">
                    <div className="h-[300px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="timestamp" 
                            type="number"
                            domain={['dataMin', 'dataMax']}
                            tickFormatter={(timestamp) => new Date(timestamp).toLocaleTimeString()}
                          />
                          <YAxis />
                          <Tooltip 
                            labelFormatter={(timestamp) => new Date(timestamp).toLocaleTimeString()}
                            formatter={(value) => [`${Number(value).toFixed(2)} ms`, 'Latency']}
                          />
                          <Legend />
                          <Line 
                            type="monotone" 
                            dataKey="connectionLatency" 
                            stroke="#3b82f6" 
                            name="Connection Latency (ms)"
                            strokeWidth={2}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </TabsContent>
                  
                  <TabsContent value="usage">
                    <div className="h-[300px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="timestamp" 
                            type="number"
                            domain={['dataMin', 'dataMax']}
                            tickFormatter={(timestamp) => new Date(timestamp).toLocaleTimeString()}
                          />
                          <YAxis />
                          <Tooltip 
                            labelFormatter={(timestamp) => new Date(timestamp).toLocaleTimeString()}
                            formatter={(value) => [`${Number(value).toFixed(1)}%`, '']}
                          />
                          <Legend />
                          <Area 
                            type="monotone" 
                            dataKey="cpuUsage" 
                            stackId="1"
                            stroke="#ef4444" 
                            fill="#ef4444"
                            fillOpacity={0.5}
                            name="CPU Usage (%)"
                          />
                          <Area 
                            type="monotone" 
                            dataKey="memoryUsage" 
                            stackId="2"
                            stroke="#8884d8" 
                            fill="#8884d8"
                            fillOpacity={0.5}
                            name="Memory Usage (%)"
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </TabsContent>
                </Tabs>
              ) : (
                <div className="text-center p-8 border rounded-lg">
                  <Server className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                  <h3 className="text-lg font-medium mb-2">No Health Data Available</h3>
                  <p className="text-muted-foreground">
                    No historical health data is available for this station yet.
                  </p>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}