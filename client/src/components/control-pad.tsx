const handleCommand = (command: string, direction: string) => {
    if (!stationId || !station) return;

    const message: WebSocketMessage = {
      type: "command",
      rpiId: station.rpiId, // Ensure RPi ID is included
      command,
      direction,
    };

    sendSocketMessage(message);
  };