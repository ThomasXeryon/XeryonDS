interface ControlPadProps {
  stationId: number;
  rpiId: string;
  enabled: boolean;
  isConnected: boolean;
  onCommand: (rpiId: string, command: string, direction?: string) => void;
}

export function ControlPad({ 
  stationId, 
  rpiId,
  enabled, 
  isConnected, 
  onCommand 
}: ControlPadProps) {

  const handleButtonClick = (direction: string) => {
    onCommand(rpiId, "move", direction);
  };

  const handleButtonRelease = () => {
    onCommand(rpiId, "stop");
  };

  // ... rest of the ControlPad component remains unchanged ...
}

const handleCommand = (rpiId: string, command: string, direction?: string) => {
    //if (!stationId || !station) return; // Removed this condition as rpiId is now directly passed.

    const message: WebSocketMessage = {
      type: "command",
      rpiId: rpiId, // Ensure RPi ID is included
      command,
      direction,
    };

    sendSocketMessage(message);
  };