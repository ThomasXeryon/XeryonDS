const sendSocketMessage = useCallback(
    (message: WebSocketMessage) => {
      if (!message.rpiId) {
        console.error("Cannot send message: No RPi ID specified", message);
        return;
      }

      if (socket && socket.readyState === WebSocket.OPEN) {
        console.log("Sending WebSocket message:", message);
        socket.send(JSON.stringify(message));
      } else {
        console.error("WebSocket not connected");
      }
    },
    [socket]
  );

const sendCommand = useCallback(
    (rpiId: string, command: string, direction?: string) => {
      const message: WebSocketMessage = {
        type: "command",
        command,
        direction,
        rpiId,
        stationId: Number(currentStationId)
      };
      sendSocketMessage(message);
    },
    [currentStationId, sendSocketMessage]
  );