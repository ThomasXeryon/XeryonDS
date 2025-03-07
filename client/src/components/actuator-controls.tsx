import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Square } from "lucide-react";
import type { WebSocketMessage } from "@shared/schema";
import { useToast } from "@/hooks/use-toast";

interface ActuatorControlsProps {
  stationId: number;
  rpiId: string;
  enabled: boolean;
  onConnectionChange: (connected: boolean, send: (msg: any) => void) => void;
}

export function ActuatorControls({ stationId, rpiId, enabled, onConnectionChange }: ActuatorControlsProps) {
  const wsRef = useRef<WebSocket>();
  const [isConnected, setIsConnected] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    if (!enabled) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      setIsConnected(true);
      onConnectionChange(true, (msg: any) => wsRef.current?.send(JSON.stringify(msg)));
      toast({
        title: "Connected to control system",
        description: "You can now control the actuator",
      });
    };

    wsRef.current.onclose = () => {
      setIsConnected(false);
      onConnectionChange(false, () => {});
      toast({
        title: "Connection lost",
        description: "Your session has ended. Thank you for using our demo station.",
        variant: "destructive",
      });
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "error") {
          toast({
            title: "Control system error",
            description: data.message,
            variant: "destructive",
          });
        } else if (data.type === "rpi_response") {
          toast({
            title: "RPi Response",
            description: data.message,
          });
        }
      } catch (err) {
        console.error("Failed to parse WebSocket message:", err);
      }
    };

    wsRef.current.onerror = () => {
      toast({
        title: "Connection error",
        description: "Failed to connect to control system",
        variant: "destructive",
      });
    };

    return () => {
      wsRef.current?.close();
    };
  }, [enabled, toast, onConnectionChange]);

  const sendCommand = (type: "move" | "stop", direction?: "up" | "down" | "left" | "right") => {
    if (!wsRef.current || !enabled || !isConnected) return;

    const message: WebSocketMessage = {
      type,
      direction,
      stationId,
      rpiId,
      command: direction ? `move_${direction}` : 'stop'
    };

    wsRef.current.send(JSON.stringify(message));
  };

  return (
    <div className="grid grid-cols-3 gap-2 max-w-[200px] mx-auto">
      <div className="col-start-2">
        <Button
          variant="outline"
          size="icon"
          disabled={!enabled || !isConnected}
          onMouseDown={() => sendCommand("move", "up")}
          onMouseUp={() => sendCommand("stop")}
          onMouseLeave={() => sendCommand("stop")}
        >
          <ChevronUp className="h-4 w-4" />
        </Button>
      </div>
      <Button
        variant="outline"
        size="icon"
        disabled={!enabled || !isConnected}
        onMouseDown={() => sendCommand("move", "left")}
        onMouseUp={() => sendCommand("stop")}
        onMouseLeave={() => sendCommand("stop")}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        disabled={!enabled || !isConnected}
      >
        <Square className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        disabled={!enabled || !isConnected}
        onMouseDown={() => sendCommand("move", "right")}
        onMouseUp={() => sendCommand("stop")}
        onMouseLeave={() => sendCommand("stop")}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
      <div className="col-start-2">
        <Button
          variant="outline"
          size="icon"
          disabled={!enabled || !isConnected}
          onMouseDown={() => sendCommand("move", "down")}
          onMouseUp={() => sendCommand("stop")}
          onMouseLeave={() => sendCommand("stop")}
        >
          <ChevronDown className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}