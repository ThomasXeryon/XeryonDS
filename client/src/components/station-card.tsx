import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CameraFeed } from "./camera-feed";
import { AdvancedControls } from "./advanced-controls";
import { SessionTimer } from "./session-timer";
import { Station } from "@shared/schema";
import { useAuth } from "@/hooks/use-auth";
import { useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { Maximize2, Minimize2, Loader2, Clock } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

type ExtendedStation = Station & {
  queueLength?: number;
  userPosition?: number | null;
  estimatedWaitTime?: number;
  remainingTime?: number;
};

export function StationCard({ station }: { station: ExtendedStation }) {
  const { user } = useAuth();
  const isMySession = station.currentUserId === user?.id;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [wsConnection, setWsConnection] = useState<{connected: boolean, send: (msg: any) => void}>({ 
    connected: false,
    send: () => {} 
  });
  const [remainingTime, setRemainingTime] = useState<number | null>(null);
  const wsRef = useRef<WebSocket>();
  const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
  const { toast } = useToast();

  // WebSocket connection handling with reconnection
  useEffect(() => {
    if (!isMySession) return;

    const connect = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        console.log("WebSocket already connected");
        return;
      }

      console.log("Attempting WebSocket connection...");
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("WebSocket connected");
        setWsConnection({
          connected: true,
          send: (msg: any) => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
              wsRef.current.send(JSON.stringify(msg));
            }
          }
        });
        toast({
          title: "Connected to control system",
          description: "You can now control the actuator",
        });
      };

      ws.onclose = () => {
        console.log("WebSocket disconnected, scheduling reconnect...");
        setWsConnection({ connected: false, send: () => {} });

        // Try to reconnect after 3 seconds
        reconnectTimeoutRef.current = setTimeout(() => {
          console.log("Attempting to reconnect...");
          connect();
        }, 3000);
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        toast({
          title: "Connection error",
          description: "Failed to connect to control system",
          variant: "destructive",
        });
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log("Received WebSocket message:", data);

          if (data.type === "session_time_update" && data.stationId === station.id) {
            setRemainingTime(data.remainingTime);
          } else if (data.type === "error") {
            toast({
              title: "Control system error",
              description: data.message,
              variant: "destructive",
            });
          }
        } catch (error) {
          console.error("Failed to parse WebSocket message:", error);
        }
      };
    };

    connect();

    return () => {
      console.log("Cleaning up WebSocket connection");
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
    };
  }, [isMySession, station.id, toast]);

  const startSession = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/stations/${station.id}/session`);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      setIsFullscreen(true);
      toast({
        title: "Session started",
        description: "You now have control of the station",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to start session",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const endSession = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("DELETE", `/api/stations/${station.id}/session`);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      setIsFullscreen(false);
      toast({
        title: "Session ended",
        description: "Thank you for using the demo station",
      });
    },
  });

  const joinQueue = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/stations/${station.id}/queue`);
      return await res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      toast({
        title: "Joined queue",
        description: `You are position ${data.position} in line. Estimated wait time: ${data.estimatedWaitTime} minutes`,
      });
    },
  });

  const leaveQueue = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("DELETE", `/api/stations/${station.id}/queue`);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      toast({
        title: "Left queue",
        description: "You have been removed from the queue",
      });
    },
  });

  const handleCommand = (command: string, value?: number) => {
    if (wsConnection.connected) {
      wsConnection.send({
        type: command,
        value,
        stationId: station.id
      });
    }
  };

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const cardClasses = isFullscreen 
    ? "fixed inset-0 z-50 m-0 rounded-none overflow-auto bg-background"
    : "";

  const renderQueueStatus = () => {
    if (station.status === "in_use" && !isMySession) {
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span>Time Remaining:</span>
            <div className="flex items-center">
              <Clock className="h-4 w-4 mr-1" />
              <span>{Math.ceil(remainingTime || station.remainingTime || 0)} minutes</span>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Queue Length: {station.queueLength || 0} users
          </p>
          {station.userPosition ? (
            <>
              <p className="text-sm text-muted-foreground">
                Your Position: {station.userPosition}
              </p>
              <p className="text-sm text-muted-foreground">
                Estimated Wait: ~{station.estimatedWaitTime} minutes
              </p>
              <Button 
                className="w-full bg-destructive hover:bg-destructive/90 transition-colors"
                onClick={() => leaveQueue.mutate()}
                disabled={leaveQueue.isPending}
              >
                {leaveQueue.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : null}
                Leave Queue
              </Button>
            </>
          ) : (
            <Button 
              className="w-full bg-primary hover:bg-primary/90 transition-colors"
              onClick={() => joinQueue.mutate()}
              disabled={joinQueue.isPending}
            >
              {joinQueue.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              Reserve Next Session
            </Button>
          )}
        </div>
      );
    }
    return null;
  };

  return (
    <Card className={cardClasses}>
      <CardHeader>
        <CardTitle className="flex justify-between items-center">
          <span>{station.name}</span>
          <div className="flex items-center gap-2">
            {isMySession && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 hover:bg-accent hover:text-accent-foreground"
                onClick={toggleFullscreen}
              >
                {isFullscreen ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </Button>
            )}
            <span className={`text-sm px-2 py-1 rounded-full ${
              station.status === "available" 
                ? "bg-green-100 text-green-700" 
                : "bg-yellow-100 text-yellow-700"
            }`}>
              {station.status === "available" ? "Available" : "In Use"}
            </span>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isFullscreen ? (
          <div className="grid grid-cols-[1fr,300px] gap-8">
            <div className="space-y-6">
              <div className="h-[600px]">
                <CameraFeed stationId={station.id} />
              </div>
              {station.sessionStart && isMySession && (
                <div className="mb-8">
                  <SessionTimer startTime={station.sessionStart} />
                </div>
              )}
            </div>
            <div className="space-y-8">
              <AdvancedControls
                stationId={station.id}
                enabled={isMySession}
                isConnected={wsConnection.connected}
                onCommand={handleCommand}
              />
              {renderQueueStatus()}
              {station.status === "available" ? (
                <Button 
                  className="w-full bg-primary hover:bg-primary/90 transition-colors"
                  onClick={() => startSession.mutate()}
                  disabled={startSession.isPending || station.userPosition !== 1}
                >
                  {startSession.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : null}
                  Start Session
                </Button>
              ) : isMySession ? (
                <Button 
                  className="w-full bg-destructive hover:bg-destructive/90 transition-colors"
                  onClick={() => endSession.mutate()}
                  disabled={endSession.isPending}
                >
                  End Session
                </Button>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="aspect-video">
              <CameraFeed stationId={station.id} />
            </div>
            {station.sessionStart && isMySession && (
              <div className="mb-4">
                <SessionTimer startTime={station.sessionStart} />
              </div>
            )}
            {renderQueueStatus()}
          </div>
        )}
      </CardContent>
    </Card>
  );
}