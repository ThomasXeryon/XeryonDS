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