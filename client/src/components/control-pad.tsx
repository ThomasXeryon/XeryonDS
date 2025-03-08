interface ControlPadProps {
  stationId: number;
  station: any; // Use proper type from your schema
  enabled: boolean;
  isConnected: boolean;
  onCommand: (rpiId: string, command: string, direction?: string) => void;
}

export function ControlPad({ 
  stationId, 
  station,
  enabled, 
  isConnected, 
  onCommand 
}: ControlPadProps) {
  // Get rpiId from station object
  const rpiId = station?.rpiId;

  const handleButtonClick = (direction: string) => {
    if (!rpiId) {
      console.error("No RPi ID available for command");
      return;
    }
    console.log(`Sending move command to RPi ${rpiId}, direction: ${direction}`);
    onCommand(rpiId, "move", direction);
  };

  const handleButtonRelease = () => {
    if (!rpiId) {
      console.error("No RPi ID available for command");
      return;
    }
    console.log(`Sending stop command to RPi ${rpiId}`);
    onCommand(rpiId, "stop");
  };

  // Get WebSocket functionality
  const { sendMessage } = useWebSocket();

  const handleArrowClick = (direction: string) => {
    if (!rpiId) return;
    sendMessage({ type: 'command', command: 'move', direction, rpiId });
  };

  const handleStopClick = () => {
    if (!rpiId) return;
    sendMessage({ type: 'command', command: 'stop', rpiId });
  };
  };