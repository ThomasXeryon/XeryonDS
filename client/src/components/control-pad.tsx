
import { Button } from "@/components/ui/button";
import { ArrowUp, ArrowDown, ArrowLeft, ArrowRight, StopCircle } from "lucide-react";
import { useWebSocket } from "@/hooks/use-websocket";

interface ControlPadProps {
  rpiId?: string | number;
  onCommand?: (rpiId: string | number, direction: string) => void;
}

export function ControlPad({ rpiId, onCommand }: ControlPadProps) {
  const { sendMessage, connectionStatus } = useWebSocket();

  const handleArrowClick = (direction: string) => {
    if (!rpiId) return;
    
    sendMessage({ 
      type: 'command', 
      command: 'move', 
      direction, 
      rpiId 
    });
    
    if (onCommand) {
      onCommand(rpiId, direction);
    }
  };

  const handleStopClick = () => {
    if (!rpiId) return;
    
    sendMessage({ 
      type: 'command', 
      command: 'stop', 
      rpiId 
    });
    
    if (onCommand) {
      onCommand(rpiId, 'stop');
    }
  };

  return (
    <div className="grid grid-cols-3 gap-2 max-w-[200px] mx-auto">
      <div className="col-start-2">
        <Button
          variant="outline"
          size="icon"
          className="w-full aspect-square"
          onClick={() => handleArrowClick('up')}
          disabled={!connectionStatus}
        >
          <ArrowUp className="h-6 w-6" />
        </Button>
      </div>
      <div className="col-start-1 row-start-2">
        <Button
          variant="outline"
          size="icon"
          className="w-full aspect-square"
          onClick={() => handleArrowClick('left')}
          disabled={!connectionStatus}
        >
          <ArrowLeft className="h-6 w-6" />
        </Button>
      </div>
      <div className="col-start-2 row-start-2">
        <Button
          variant="outline"
          size="icon"
          className="w-full aspect-square bg-red-100 hover:bg-red-200"
          onClick={handleStopClick}
          disabled={!connectionStatus}
        >
          <StopCircle className="h-6 w-6 text-red-500" />
        </Button>
      </div>
      <div className="col-start-3 row-start-2">
        <Button
          variant="outline"
          size="icon"
          className="w-full aspect-square"
          onClick={() => handleArrowClick('right')}
          disabled={!connectionStatus}
        >
          <ArrowRight className="h-6 w-6" />
        </Button>
      </div>
      <div className="col-start-2 row-start-3">
        <Button
          variant="outline"
          size="icon"
          className="w-full aspect-square"
          onClick={() => handleArrowClick('down')}
          disabled={!connectionStatus}
        >
          <ArrowDown className="h-6 w-6" />
        </Button>
      </div>
    </div>
  );
}
