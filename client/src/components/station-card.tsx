import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CameraFeed } from "./camera-feed";
import { ActuatorControls } from "./actuator-controls";
import { AdvancedControls } from "./advanced-controls";
import { SessionTimer } from "./session-timer";
import { Station } from "@shared/schema";
import { useAuth } from "@/hooks/use-auth";
import { useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { Maximize2, Minimize2 } from "lucide-react";

export function StationCard({ station }: { station: Station }) {
  const { user } = useAuth();
  const isMySession = station.currentUserId === user?.id;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [wsConnection, setWsConnection] = useState<{connected: boolean, send: (msg: any) => void}>({ 
    connected: false,
    send: () => {} 
  });

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
      wsConnection.send(JSON.stringify({
        type: command,
        value,
        stationId: station.id
      }));
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
        <div className={`grid ${isFullscreen ? 'grid-cols-2 gap-8' : 'grid-cols-1 gap-6'}`}>
          <div className="space-y-6">
            <CameraFeed stationId={station.id} />
            <ActuatorControls 
              stationId={station.id} 
              enabled={isMySession}
              onConnectionChange={(connected, sendFn) => 
                setWsConnection({ connected, send: sendFn })}
            />
          </div>

          {isFullscreen && (
            <div className="space-y-6">
              <AdvancedControls
                stationId={station.id}
                enabled={isMySession}
                isConnected={wsConnection.connected}
                onCommand={handleCommand}
              />
              {station.sessionStart && isMySession && (
                <SessionTimer startTime={station.sessionStart} />
              )}
            </div>
          )}
        </div>

        {!isFullscreen && station.sessionStart && isMySession && (
          <SessionTimer startTime={station.sessionStart} />
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