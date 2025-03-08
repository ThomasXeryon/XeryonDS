import React, { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CameraFeed } from "@/components/camera-feed";
import { AdvancedControls } from "./advanced-controls";
import { SessionTimer } from "./session-timer";
import { Station } from "@shared/schema";
import { useAuth } from "@/hooks/use-auth";
import { useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { Maximize2, Minimize2, CreditCard, Mail, MessageSquare } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

export function StationCard({ station }: { station: Station }) {
  const { user } = useAuth();
  const isMySession = station.currentUserId === user?.id;
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showThankYouDialog, setShowThankYouDialog] = useState(false);
  const [feedback, setFeedback] = useState("");

  // Reset dialog state when component updates
  useEffect(() => {
    if (!isMySession) {
      setShowThankYouDialog(false);
    }
  }, [isMySession]);
  const [wsConnection, setWsConnection] = useState<{connected: boolean, send: (msg: any) => void}>({ 
    connected: false,
    send: () => {} 
  });
  const wsRef = useRef<WebSocket>();
  const { toast } = useToast();

  const startSession = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/stations/${station.id}/start-session`);
      return res.json();
    },
    onSuccess: () => {
      toast({
        title: "Session started",
        description: "You now have control of the demo station",
      });
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to start session",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const endSession = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/stations/${station.id}/end-session`);
      return res.json();
    },
    onSuccess: () => {
      toast({
        title: "Session ended",
        description: "Thank you for using the demo station",
      });
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      setShowThankYouDialog(true); // Show dialog here after successful end
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to end session",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const submitFeedback = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/stations/${station.id}/feedback`, { 
        feedback 
      });
      return res.json();
    },
    onSuccess: () => {
      toast({
        title: "Feedback submitted",
        description: "Thank you for your feedback",
      });
      setFeedback("");
      setShowThankYouDialog(false);
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to submit feedback",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const handleCommand = (command: string, direction: string) => {
    console.log("Sending command:", command, "direction:", direction);
    if (wsConnection.connected) {
      wsConnection.send({ command, direction });
    }
  };

  const handleFeedbackSubmit = () => {
    if (feedback.trim()) {
      submitFeedback.mutate();
    }
  };

  // Compute classes dynamically based on fullscreen state
  const cardClasses = isFullscreen 
    ? "fixed inset-4 z-50 overflow-auto" 
    : "transition-all";

  // Connect to WebSocket for station
  useEffect(() => {
    if (!user) return;

    console.log("RPi ID:", station.rpiId);
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    console.log("Connecting to WebSocket at:", wsUrl);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("WebSocket connected");
      setWsConnection({
        connected: true,
        send: (msg) => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              ...msg,
              stationId: station.id,
              rpiId: station.rpiId
            }));
          }
        }
      });
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      setWsConnection({
        connected: false,
        send: () => {}
      });
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [station.id, station.rpiId, user]);

  return (
    <>
      <Card className={cardClasses}>
        <CardHeader>
          <CardTitle className="flex justify-between items-center">
            <span>{station.name}</span>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 hover:bg-accent hover:text-accent-foreground"
                onClick={toggleFullscreen}
              >
                {isFullscreen ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </Button>
              <span className={`text-sm px-2 py-1 rounded-full ${
                station.status === "available" 
                  ? "bg-green-100 text-green-700" 
                  : "bg-yellow-100 text-yellow-700"
              }`}>
                {station.status === "available" ? "Available" : "In Use"}
              </span>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isFullscreen ? (
            // Fullscreen layout - keep camera feed full width
            <div className="grid grid-cols-[1fr,300px] gap-8">
              <div className="space-y-6">
                <div className="h-[600px]">
                  <CameraFeed rpiId={station.rpiId} />
                </div>
              </div>
              <div className="space-y-8">
                <AdvancedControls
                  stationId={station.id}
                  enabled={isMySession}
                  isConnected={wsConnection.connected}
                  onCommand={handleCommand}
                />
                {station.sessionStart && isMySession && (
                  <div>
                    <SessionTimer 
                      startTime={station.sessionStart} 
                      onTimeout={() => {
                        if (!endSession.isPending) {
                          endSession.mutate();
                          // Dialog will be shown in onSuccess handler
                        }
                      }}
                    />
                  </div>
                )}
                {station.status === "available" ? (
                  <Button 
                    className="w-full bg-primary hover:bg-primary/90 transition-colors"
                    onClick={() => startSession.mutate()}
                    disabled={startSession.isPending}
                  >
                    Start Session
                  </Button>
                ) : isMySession ? (
                  <Button 
                    className="w-full hover:bg-destructive/90 transition-colors"
                    variant="destructive"
                    onClick={() => {
                      endSession.mutate();
                      // Only show dialog once when session ends
                      if (!showThankYouDialog) {
                        setShowThankYouDialog(true);
                      }
                    }}
                    disabled={endSession.isPending}
                  >
                    End Session
                  </Button>
                ) : (
                  <Button className="w-full" disabled>
                    In Use by Another User
                  </Button>
                )}
              </div>
            </div>
          ) : (
            // Regular layout - grid with camera feed on top
            <div className="space-y-6">
              <div className="aspect-video rounded-lg overflow-hidden bg-muted">
                {station.previewImage && !wsConnection.connected ? (
                  <img
                    src={station.previewImage}
                    alt={`${station.name} preview`}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <CameraFeed rpiId={station.rpiId} />
                )}
              </div>
              <div className="grid grid-cols-2 gap-4">
                <AdvancedControls
                  stationId={station.id}
                  enabled={isMySession}
                  isConnected={wsConnection.connected}
                  onCommand={handleCommand}
                />
                <div className="space-y-4">
                  {station.sessionStart && isMySession && (
                    <SessionTimer 
                      startTime={station.sessionStart} 
                      onTimeout={() => {
                        if (!endSession.isPending) {
                          endSession.mutate();
                          // Dialog will be shown in onSuccess handler
                        }
                      }}
                    />
                  )}
                  {station.status === "available" ? (
                    <Button 
                      className="w-full"
                      onClick={() => startSession.mutate()}
                      disabled={startSession.isPending}
                    >
                      Start Session
                    </Button>
                  ) : isMySession ? (
                    <Button 
                      className="w-full"
                      variant="destructive"
                      onClick={() => {
                        endSession.mutate();
                        // Only show dialog once when session ends
                        if (!showThankYouDialog) {
                          setShowThankYouDialog(true);
                        }
                      }}
                      disabled={endSession.isPending}
                    >
                      End Session
                    </Button>
                  ) : (
                    <Button className="w-full" disabled>
                      In Use by Another User
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog 
  open={showThankYouDialog} 
  onOpenChange={(open) => {
    setShowThankYouDialog(open);
    if (!open) {
      setFeedback(""); // Reset feedback when dialog closes
    }
  }}
>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Thank You!</DialogTitle>
            <DialogDescription>
              Your session has ended. We hope you enjoyed using the remote demo station.
            </DialogDescription>
          </DialogHeader>
          <div>
            <div className="space-y-4 pt-4 border-t">
              <Label htmlFor="feedback">Quick Feedback</Label>
              <Textarea
                id="feedback"
                placeholder="Share your experience with the demo station..."
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                className="min-h-[100px]"
              />
              <Button 
                className="w-full"
                onClick={() => {
                  handleFeedbackSubmit();
                  setShowThankYouDialog(false); // Close dialog after submitting
                }}
                disabled={submitFeedback.isPending || !feedback.trim()}
              >
                <MessageSquare className="h-4 w-4 mr-2" />
                Submit Feedback
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}