import { useState, useEffect } from 'react';
import { useRoute } from 'wouter';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, 
  ResponsiveContainer 
} from 'recharts';
import { 
  Play, Pause, SkipBack, SkipForward, 
  Clock, Activity, BarChart, Command 
} from "lucide-react";

interface SessionReplayData {
  session: {
    id: number;
    stationId: number;
    userId: number;
    startTime: string;
    endTime: string | null;
    commandCount: number;
  };
  positions: Array<{
    id: number;
    sessionLogId: number;
    position: number;
    timestamp: string;
    command_type?: string;
    command_direction?: string;
    command_step_size?: number;
    command_step_unit?: string;
  }>;
  commands: Array<{
    id: number;
    sessionLogId: number;
    command: string;
    direction?: string;
    step_size?: number;
    step_unit?: string;
    parameters?: any;
    timestamp: string;
  }>;
}

export function SessionReplayPage() {
  const [, params] = useRoute('/session-replay/:sessionId');
  const sessionId = params?.sessionId;
  
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [currentPosition, setCurrentPosition] = useState<number | null>(null);
  const [playbackInterval, setPlaybackInterval] = useState<number | null>(null);
  
  // Fetch session replay data
  const { data, isLoading, error } = useQuery({
    queryKey: ['/api/session-replay', sessionId],
    queryFn: async () => {
      const response = await fetch(`/api/session-replay/${sessionId}`);
      if (!response.ok) {
        throw new Error('Failed to fetch session replay data');
      }
      return response.json() as Promise<SessionReplayData>;
    },
    enabled: !!sessionId
  });
  
  // Calculate session duration once data is loaded
  useEffect(() => {
    if (data?.positions && data.positions.length > 0) {
      const startTimestamp = new Date(data.positions[0].timestamp).getTime();
      const endTimestamp = new Date(data.positions[data.positions.length - 1].timestamp).getTime();
      setDuration(endTimestamp - startTimestamp);
    }
  }, [data]);
  
  // Handle play/pause
  const togglePlayback = () => {
    if (isPlaying) {
      // Pause playback
      if (playbackInterval) {
        clearInterval(playbackInterval);
        setPlaybackInterval(null);
      }
    } else {
      // Start playback
      const interval = window.setInterval(() => {
        setCurrentTime(prevTime => {
          const newTime = prevTime + (100 * playbackSpeed);
          if (newTime >= duration) {
            clearInterval(interval);
            setIsPlaying(false);
            return duration;
          }
          return newTime;
        });
      }, 100);
      setPlaybackInterval(interval as unknown as number);
    }
    setIsPlaying(!isPlaying);
  };
  
  // Update current position based on current time
  useEffect(() => {
    if (data?.positions && data.positions.length > 0) {
      const startTimestamp = new Date(data.positions[0].timestamp).getTime();
      const currentTimestamp = startTimestamp + currentTime;
      
      // Find the closest position to current time
      let closestPosition = data.positions[0].position;
      let closestDiff = Infinity;
      
      for (const pos of data.positions) {
        const posTimestamp = new Date(pos.timestamp).getTime();
        const diff = Math.abs(posTimestamp - currentTimestamp);
        if (diff < closestDiff) {
          closestDiff = diff;
          closestPosition = pos.position;
        }
      }
      
      setCurrentPosition(closestPosition);
    }
  }, [currentTime, data]);
  
  // Clean up interval on unmount
  useEffect(() => {
    return () => {
      if (playbackInterval) {
        clearInterval(playbackInterval);
      }
    };
  }, [playbackInterval]);
  
  // Reset playback
  const resetPlayback = () => {
    setCurrentTime(0);
    if (isPlaying) {
      togglePlayback(); // Stop playback
    }
  };
  
  // Format timestamp for display
  const formatTime = (milliseconds: number) => {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
  };
  
  // Skip forward/backward
  const skip = (amount: number) => {
    setCurrentTime(prevTime => {
      const newTime = prevTime + amount;
      return Math.max(0, Math.min(newTime, duration));
    });
  };
  
  if (isLoading) {
    return <div className="flex justify-center items-center min-h-screen">Loading session data...</div>;
  }
  
  if (error || !data) {
    return (
      <div className="p-4">
        <Card className="max-w-4xl mx-auto">
          <CardHeader>
            <CardTitle className="text-red-500">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p>Failed to load session replay data. Please try again.</p>
            <Button variant="default" className="mt-4" onClick={() => window.history.back()}>
              Go Back
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }
  
  // Prepare data for charts
  const positionChartData = data.positions.map(pos => ({
    timestamp: new Date(pos.timestamp).getTime(),
    position: pos.position,
    formattedTime: new Date(pos.timestamp).toLocaleTimeString()
  }));
  
  return (
    <div className="p-4">
      <Card className="max-w-5xl mx-auto">
        <CardHeader>
          <CardTitle>Session Replay</CardTitle>
          <CardDescription>
            Session ID: {data.session.id} | 
            Date: {new Date(data.session.startTime).toLocaleDateString()} | 
            Commands: {data.session.commandCount}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-8">
            <div className="text-3xl font-bold text-center text-primary mb-4">
              Current Position: {currentPosition !== null ? currentPosition.toFixed(3) : '–'} mm
            </div>
            
            <div className="h-[300px] mb-4">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={positionChartData}>
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
                    formatter={(value) => [`${Number(value).toFixed(3)} mm`, 'Position']}
                  />
                  <Legend />
                  <Line 
                    type="monotone" 
                    dataKey="position" 
                    stroke="#3b82f6" 
                    strokeWidth={2}
                    dot={false}
                    name="Position (mm)"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            
            <div className="flex justify-between items-center mb-2">
              <div>{formatTime(currentTime)}</div>
              <div>{formatTime(duration)}</div>
            </div>
            
            <div className="w-full bg-gray-200 dark:bg-gray-700 h-2 rounded-full mb-4">
              <div 
                className="bg-primary h-2 rounded-full"
                style={{ width: `${(currentTime / duration) * 100}%` }}
              ></div>
            </div>
            
            <div className="flex justify-center items-center gap-2">
              <Button 
                variant="outline" 
                size="icon"
                onClick={() => skip(-5000)}
              >
                <SkipBack className="h-4 w-4" />
              </Button>
              
              <Button 
                variant="default" 
                size="icon"
                onClick={togglePlayback}
              >
                {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              </Button>
              
              <Button 
                variant="outline" 
                size="icon"
                onClick={() => skip(5000)}
              >
                <SkipForward className="h-4 w-4" />
              </Button>
              
              <Button 
                variant="outline" 
                size="icon"
                onClick={resetPlayback}
              >
                <SkipBack className="h-4 w-4" fill="currentColor" />
              </Button>
            </div>
          </div>
          
          <Separator className="my-4" />
          
          <Tabs defaultValue="commands">
            <TabsList className="mb-4">
              <TabsTrigger value="commands">
                <Command className="h-4 w-4 mr-2" />
                Commands
              </TabsTrigger>
              <TabsTrigger value="session">
                <Clock className="h-4 w-4 mr-2" />
                Session Info
              </TabsTrigger>
            </TabsList>
            
            <TabsContent value="commands">
              <div className="max-h-60 overflow-y-auto border rounded-md">
                <table className="w-full">
                  <thead className="sticky top-0 bg-background">
                    <tr>
                      <th className="p-2 text-left">Time</th>
                      <th className="p-2 text-left">Command</th>
                      <th className="p-2 text-left">Direction</th>
                      <th className="p-2 text-left">Size</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.commands.map(cmd => (
                      <tr key={cmd.id} className="border-t">
                        <td className="p-2">{new Date(cmd.timestamp).toLocaleTimeString()}</td>
                        <td className="p-2 font-semibold">{cmd.command}</td>
                        <td className="p-2">{cmd.direction || '–'}</td>
                        <td className="p-2">
                          {cmd.step_size ? `${cmd.step_size} ${cmd.step_unit || 'mm'}` : '–'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </TabsContent>
            
            <TabsContent value="session">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <h3 className="font-semibold mb-2">Session Details</h3>
                  <div className="space-y-2">
                    <p><span className="font-medium">Start Time:</span> {new Date(data.session.startTime).toLocaleString()}</p>
                    <p><span className="font-medium">End Time:</span> {data.session.endTime ? new Date(data.session.endTime).toLocaleString() : 'Session still active'}</p>
                    <p><span className="font-medium">Duration:</span> {formatTime(duration)}</p>
                    <p><span className="font-medium">Total Commands:</span> {data.session.commandCount}</p>
                  </div>
                </div>
                
                <div>
                  <h3 className="font-semibold mb-2">Position Statistics</h3>
                  <div className="space-y-2">
                    {data.positions.length > 0 && (
                      <>
                        <p>
                          <span className="font-medium">Min Position:</span> {Math.min(...data.positions.map(p => p.position)).toFixed(3)} mm
                        </p>
                        <p>
                          <span className="font-medium">Max Position:</span> {Math.max(...data.positions.map(p => p.position)).toFixed(3)} mm
                        </p>
                        <p>
                          <span className="font-medium">Average Position:</span> {(data.positions.reduce((sum, p) => sum + p.position, 0) / data.positions.length).toFixed(3)} mm
                        </p>
                        <p>
                          <span className="font-medium">Data Points:</span> {data.positions.length}
                        </p>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}