import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Square } from "lucide-react";
import type { WebSocketMessage } from "@shared/schema";

export function ActuatorControls({ stationId, enabled }: { stationId: number; enabled: boolean }) {
  const wsRef = useRef<WebSocket>();

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    wsRef.current = new WebSocket(wsUrl);

    return () => {
      wsRef.current?.close();
    };
  }, []);

  const sendCommand = (type: "move" | "stop", direction?: "up" | "down" | "left" | "right") => {
    if (!wsRef.current || !enabled) return;

    const message: WebSocketMessage = {
      type,
      direction,
      stationId,
    };

    wsRef.current.send(JSON.stringify(message));
  };

  return (
    <div className="grid grid-cols-3 gap-2 max-w-[200px] mx-auto">
      <div className="col-start-2">
        <Button
          variant="outline"
          size="icon"
          disabled={!enabled}
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
        disabled={!enabled}
        onMouseDown={() => sendCommand("move", "left")}
        onMouseUp={() => sendCommand("stop")}
        onMouseLeave={() => sendCommand("stop")}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        disabled={!enabled}
      >
        <Square className="h-4 w-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        disabled={!enabled}
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
          disabled={!enabled}
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
