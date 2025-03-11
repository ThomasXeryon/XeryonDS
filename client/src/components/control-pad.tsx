import { Button } from "@/components/ui/button";
import { ArrowUp, ArrowDown, ArrowLeft, ArrowRight, StopCircle } from "lucide-react";
import { useWebSocket } from "@/hooks/use-websocket";

interface ControlPadProps {
  rpiId?: string | number;
  onCommand?: (rpiId: string | number, command: string) => void;
}

export function ControlPad({ rpiId, onCommand = () => {} }: ControlPadProps) {
  const { sendMessage } = useWebSocket();

  const handleArrowClick = (direction: string) => {
    if (!rpiId) {
      console.error("[ControlPad] Cannot send command - rpiId is missing");
      return;
    }

    console.log("[ControlPad] Sending move command:", { direction, rpiId });
    sendMessage({ 
      type: 'command', 
      command: 'move', 
      direction, 
      rpiId 
    });

    onCommand(rpiId, direction);
  };

  const handleStopClick = () => {
    if (!rpiId) {
      console.error("[ControlPad] Cannot send command - rpiId is missing");
      return;
    }

    console.log("[ControlPad] Sending stop command:", { rpiId });
    sendMessage({ 
      type: 'command', 
      command: 'stop', 
      rpiId 
    });

    onCommand(rpiId, 'stop');
  };

  if (!rpiId) {
    console.warn("[ControlPad] No rpiId provided");
    return null;
  }

  return (
    <div className="grid grid-cols-3 gap-2 max-w-[180px] mx-auto">
      <div></div>
      <Button 
        variant="secondary" 
        size="sm" 
        onClick={() => handleArrowClick('up')}
        className="p-2 h-auto"
      >
        <ArrowUp className="h-5 w-5" />
      </Button>
      <div></div>

      <Button 
        variant="secondary" 
        size="sm" 
        onClick={() => handleArrowClick('left')}
        className="p-2 h-auto"
      >
        <ArrowLeft className="h-5 w-5" />
      </Button>

      <Button 
        variant="secondary" 
        size="sm" 
        onClick={handleStopClick}
        className="p-2 h-auto"
      >
        <StopCircle className="h-5 w-5" />
      </Button>

      <Button 
        variant="secondary" 
        size="sm" 
        onClick={() => handleArrowClick('right')}
        className="p-2 h-auto"
      >
        <ArrowRight className="h-5 w-5" />
      </Button>

      <div></div>
      <Button 
        variant="secondary" 
        size="sm" 
        onClick={() => handleArrowClick('down')}
        className="p-2 h-auto"
      >
        <ArrowDown className="h-5 w-5" />
      </Button>
      <div></div>
    </div>
  );
}