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
import { Maximize2, Minimize2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

export function StationCard({ station }: { station: Station }) {
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
    },
  });

  const endSession = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("DELETE", `/api/stations/${station.id}/session`);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
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

  return (
    <Card className={cardClasses}>
      <CardHeader>
        <CardTitle className="flex justify-between items-center">
          <span>{station.name}</span>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
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
      <CardContent className="space-y-6">
        {isFullscreen ? (
          // Fullscreen layout
          <div className="grid grid-cols-[1fr,300px] gap-8">
            <div className="space-y-6">
              <CameraFeed stationId={station.id} />
              {station.sessionStart && isMySession && (
                <SessionTimer startTime={station.sessionStart} />
              )}
            </div>
            <div>
              <AdvancedControls
                stationId={station.id}
                enabled={isMySession}
                isConnected={wsConnection.connected}
                onCommand={handleCommand}
              />
            </div>
          </div>
        ) : (
          // Overview layout
          <div className="space-y-6">
            <div className="aspect-video">
              <CameraFeed stationId={station.id} />
            </div>
            {station.sessionStart && isMySession && (
              <SessionTimer startTime={station.sessionStart} />
            )}
          </div>
        )}

        {station.status === "available" ? (
          <Button 
            className="w-full" 
            onClick={() => startSession.mutate()}
            disabled={startSession.isPending}
          >
            Start Session
          </Button>
        ) : isMySession ? (
          <Button 
            className="w-full" 
            variant="outline"
            onClick={() => endSession.mutate()}
            disabled={endSession.isPending}
          >
            End Session
          </Button>
        ) : (
          <Button className="w-full" disabled>
            Station Occupied
          </Button>
        )}
      </CardContent>
    </Card>
  );
}