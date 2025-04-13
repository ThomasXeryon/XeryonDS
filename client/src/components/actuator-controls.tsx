import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Home } from "lucide-react";
import type { WebSocketMessage } from "@shared/schema";
import { useToast } from "@/hooks/use-toast";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
  const [stepSize, setStepSize] = useState<string>("1.0");
  const [stepUnit, setStepUnit] = useState<string>("mm");
  const [acce, setAcce] = useState<number | undefined>(undefined); // Acceleration parameter from advanced controls
  const [dece, setDece] = useState<number | undefined>(undefined); // Deceleration parameter from advanced controls
  let reconnectAttempts = 0;
  const maxReconnectAttempts = 5;
  let reconnectTimer: number | null = null;


  useEffect(() => {
    if (!enabled) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/appws`;

    // Close existing connection if it exists
    if (wsRef.current) {
      wsRef.current.close();
    }

    // Helper function to initialize WebSocket
    function initWebSocket() {
      const ws = new WebSocket(wsUrl);

      ws.onmessage = (event) => {
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
      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      // Handle open event
      ws.onopen = () => {
        setIsConnected(true);
        onConnectionChange(true, (msg: any) => {
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(msg));
          }
        });
        reconnectAttempts = 0;
        console.log('WebSocket connected');

        // Register with the server to receive messages for this station
        const registerMsg = {
          type: "register",
          stationId,
          rpiId
        };
        ws.send(JSON.stringify(registerMsg));

        toast({
          title: "Connected to control system",
          description: "You can now control the actuator",
        });
      };

      // Add connection close handler with reconnection logic
      ws.onclose = () => {
        setIsConnected(false);
        onConnectionChange(false, () => {});
        console.log('WebSocket connection closed');

        // Implement reconnection with exponential backoff
        if (reconnectAttempts < maxReconnectAttempts) {
          const backoffTime = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
          console.log(`Attempting to reconnect in ${backoffTime}ms (attempt ${reconnectAttempts + 1}/${maxReconnectAttempts})`);

          reconnectTimer = window.setTimeout(() => {
            reconnectAttempts++;
            initWebSocket();
          }, backoffTime) as unknown as number;
        } else {
          toast({
            title: "Connection lost",
            description: "Maximum reconnection attempts reached. Please check your connection.",
            variant: "destructive",
          });
          console.error('Maximum reconnection attempts reached');
        }
      };

      wsRef.current = ws;
      return ws;
    }

    // Initialize the first connection
    initWebSocket();

    // Cleanup function
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = undefined;
      }

      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
    };
  }, [enabled, toast, onConnectionChange, stationId, rpiId]);

  const sendCommand = (type: "move" | "stop" | "step" | "home", direction?: "up" | "down" | "left" | "right") => {
    if (!wsRef.current || !enabled || !isConnected) {
      console.log("Cannot send command - connection not ready", { enabled, isConnected });
      return;
    }

    let commandStr = 'stop';
    if (type === 'home') {
      commandStr = 'home';
    } else if (direction) {
      commandStr = `move_${direction}`;
    }

    const message: WebSocketMessage = {
      type,
      direction,
      stationId,
      rpiId,
      command: commandStr,
      stepSize: parseFloat(stepSize),
      stepUnit,
      acce, // Include acceleration parameter if available
      dece  // Include deceleration parameter if available
    };

    try {
      console.log("Sending command:", message);
      wsRef.current.send(JSON.stringify(message));
    } catch (err) {
      console.error("Failed to send command:", err);
      toast({
        title: "Command failed",
        description: "Could not send command to the control system",
        variant: "destructive",
      });
    }
  };

  // Handle step size input change
  const handleStepSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Only allow numeric values with up to one decimal point
    if (/^\d*\.?\d*$/.test(value)) {
      setStepSize(value);
    }
  };

  // Handle step command with step size and units
  const handleStepCommand = (direction: "up" | "down" | "left" | "right") => {
    // The sendCommand function already includes stepSize and stepUnit in the message
    sendCommand("step", direction);
  };

  return (
    <div className="flex flex-col gap-4 max-w-[250px] mx-auto">
      {/* Step size controls */}
      <div className="flex items-center gap-2 mb-2">
        <Label htmlFor="stepSize" className="text-xs whitespace-nowrap">Step Size:</Label>
        <div className="flex-1">
          <Input
            id="stepSize"
            type="text"
            value={stepSize}
            onChange={handleStepSizeChange}
            className="h-8 text-xs"
            disabled={!enabled || !isConnected}
          />
        </div>
        <Select 
          value={stepUnit} 
          onValueChange={setStepUnit}
          disabled={!enabled || !isConnected}
        >
          <SelectTrigger className="h-8 w-16 text-xs">
            <SelectValue placeholder="Unit" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="mm">mm</SelectItem>
            <SelectItem value="µm">µm</SelectItem>
            <SelectItem value="nm">nm</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Direction controls */}
      <div className="grid grid-cols-3 gap-3 w-full max-w-[180px] mx-auto mt-2">
        <div className="col-start-2 flex justify-center">
          <Button
            variant="outline"
            size="icon"
            className="w-12 h-12 shadow-sm border-2"
            disabled={!enabled || !isConnected}
            onMouseDown={() => sendCommand("move", "up")}
            onMouseUp={() => sendCommand("stop")}
            onMouseLeave={() => sendCommand("stop")}
            onDoubleClick={() => handleStepCommand("up")}
          >
            <ChevronUp className="h-6 w-6" />
          </Button>
        </div>
        <div className="flex justify-center items-center">
          <Button
            variant="outline"
            size="icon"
            className="w-12 h-12 shadow-sm border-2"
            disabled={!enabled || !isConnected}
            onMouseDown={() => sendCommand("move", "left")}
            onMouseUp={() => sendCommand("stop")}
            onMouseLeave={() => sendCommand("stop")}
            onDoubleClick={() => handleStepCommand("left")}
          >
            <ChevronLeft className="h-6 w-6" />
          </Button>
        </div>
        <div className="flex justify-center items-center">
          <Button
            variant="default"
            size="icon"
            className="w-12 h-12 bg-white text-primary hover:bg-slate-100 font-semibold border-2 border-primary shadow-md"
            disabled={!enabled || !isConnected}
            onClick={() => sendCommand("home")}
          >
            <Home className="h-6 w-6" />
          </Button>
        </div>
        <div className="flex justify-center items-center">
          <Button
            variant="outline"
            size="icon"
            className="w-12 h-12 shadow-sm border-2"
            disabled={!enabled || !isConnected}
            onMouseDown={() => sendCommand("move", "right")}
            onMouseUp={() => sendCommand("stop")}
            onMouseLeave={() => sendCommand("stop")}
            onDoubleClick={() => handleStepCommand("right")}
          >
            <ChevronRight className="h-6 w-6" />
          </Button>
        </div>
        <div className="col-start-2 flex justify-center">
          <Button
            variant="outline"
            size="icon"
            className="w-12 h-12 shadow-sm border-2"
            disabled={!enabled || !isConnected}
            onMouseDown={() => sendCommand("move", "down")}
            onMouseUp={() => sendCommand("stop")}
            onMouseLeave={() => sendCommand("stop")}
            onDoubleClick={() => handleStepCommand("down")}
          >
            <ChevronDown className="h-6 w-6" />
          </Button>
        </div>
      </div>
    </div>
  );
}