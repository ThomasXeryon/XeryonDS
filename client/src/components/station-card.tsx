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
import { Maximize2, Minimize2, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

type ExtendedStation = Station & {
  queueLength?: number;
  userPosition?: number | null;
  estimatedWaitTime?: number;
};

export function StationCard({ station }: { station: ExtendedStation }) {
  const { user } = useAuth();
  const isMySession = station.currentUserId === user?.id;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [wsConnection, setWsConnection] = useState<{connected: boolean, send: (msg: any) => void}>({ 
    connected: false,
    send: () => {} 
  });
  const wsRef = useRef<WebSocket>();
  const { toast } = useToast();

  // WebSocket connection handling
  useEffect(() => {
    if (!isMySession) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      setWsConnection({
        connected: true,
        send: (msg: any) => wsRef.current?.send(JSON.stringify(msg))
      });
      toast({
        title: "Connected to control system",
        description: "You can now control the actuator",
      });
    };

    wsRef.current.onclose = () => {
      setWsConnection({ connected: false, send: () => {} });
      toast({
        title: "Disconnected from control system",
        description: "Please refresh the page to reconnect",
        variant: "destructive",
      });
    };

    wsRef.current.onerror = () => {
      toast({
        title: "Connection error",
        description: "Failed to connect to control system",
        variant: "destructive",
      });
    };

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "error") {
        toast({
          title: "Control system error",
          description: data.message,
          variant: "destructive",
        });
      }
    };

    return () => {
      wsRef.current?.close();
    };
  }, [isMySession, toast]);

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
              Join Queue
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
          // Fullscreen layout
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
                  className="w-full hover:bg-destructive/90 transition-colors"
                  variant="destructive"
                  onClick={() => endSession.mutate()}
                  disabled={endSession.isPending}
                >
                  End Session
                </Button>
              ) : station.userPosition ? (
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
              ) : null}
            </div>
          </div>
        ) : (
          // Overview layout
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
            {station.status === "available" ? (
              <Button 
                className="w-full bg-primary hover:bg-primary/90 transition-colors"
                onClick={() => startSession.mutate()}
                disabled={startSession.isPending || station.userPosition !== 1}
              >
                Start Session
              </Button>
            ) : isMySession ? (
              <Button 
                className="w-full hover:bg-destructive/90 transition-colors"
                variant="destructive"
                onClick={() => endSession.mutate()}
                disabled={endSession.isPending}
              >
                End Session
              </Button>
            ) : station.userPosition ? (
              <Button 
                className="w-full bg-destructive hover:bg-destructive/90 transition-colors"
                onClick={() => leaveQueue.mutate()}
                disabled={leaveQueue.isPending}
              >
                Leave Queue
              </Button>
            ) : null}
          </div>
        )}
      </CardContent>
    </Card>
  );
}