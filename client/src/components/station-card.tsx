import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CameraFeed } from "./camera-feed";
import { ActuatorControls } from "./actuator-controls";
import { SessionTimer } from "./session-timer";
import { Station } from "@shared/schema";
import { useAuth } from "@/hooks/use-auth";
import { useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";

export function StationCard({ station }: { station: Station }) {
  const { user } = useAuth();
  const isMySession = station.currentUserId === user?.id;
  
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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex justify-between items-center">
          <span>{station.name}</span>
          <span className={`text-sm px-2 py-1 rounded-full ${
            station.status === "available" 
              ? "bg-green-100 text-green-700" 
              : "bg-yellow-100 text-yellow-700"
          }`}>
            {station.status === "available" ? "Available" : "In Use"}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <CameraFeed stationId={station.id} />
        
        <ActuatorControls 
          stationId={station.id} 
          enabled={isMySession} 
        />
        
        {station.sessionStart && isMySession && (
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
