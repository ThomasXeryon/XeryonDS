import { useState, useEffect, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CameraFeed } from "./camera-feed";
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
  const [wsConnection, setWsConnection] = useState<{
    connected: boolean;
    send: (msg: any) => void;
  }>({
    connected: false,
    send: () => {},
  });
  const wsRef = useRef<WebSocket>();
  const { toast } = useToast();

  // WebSocket connection handling
  useEffect(() => {
    if (!isMySession) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      setWsConnection({
        connected: true,
        send: (msg: any) => wsRef.current?.send(JSON.stringify(msg)),
      });
      toast({
        title: "Connected to control system",
        description: "You can now control the actuator",
      });
    };

    wsRef.current.onclose = () => {
      setWsConnection({ connected: false, send: () => {} });
      toast({
        title: "Connection lost",
        description: "Your session has ended. Thank you for using our demo station.",
        variant: "destructive",
      });
    };

    wsRef.current.onerror = () => {
      toast({
        title: "Connection error",
        description: "Failed to connect to control system",
        variant: "destructive",
      });
    };

    wsRef.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "error") {
        toast({
          title: "Control system error",
          description: data.message,
          variant: "destructive",
        });
      }
    };

    return () => {
      wsRef.current?.close();
    };
  }, [isMySession, toast]);

  const startSession = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", `/api/stations/${station.id}/session`);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      setIsFullscreen(true); // Auto fullscreen on session start
      toast({
        title: "Session started",
        description: "You now have control of the station",
      });
    },
  });

  const endSession = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("DELETE", `/api/stations/${station.id}/session`);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      setIsFullscreen(false); // Back to overview on session end
      setShowThankYouDialog(true); // Show thank you dialog
    },
  });

  const submitFeedback = useMutation({
    mutationFn: async (feedback: string) => {
      const res = await apiRequest("POST", "/api/feedback", {
        type: "feedback",
        message: feedback,
      });
      return res.json();
    },
    onSuccess: () => {
      toast({
        title: "Thank you for your feedback!",
        description: "Your feedback has been submitted successfully.",
      });
      setFeedback("");
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to submit feedback",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleCommand = (command: string, value?: number) => {
    if (wsConnection.connected) {
      wsConnection.send({
        type: command,
        value,
        stationId: station.id,
        rpiId: station.rpiId // Added rpiId
      });
    }
  };

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen);
  };

  const handleContactUs = () => {
    window.open("https://xeryon.com/contact/", "_blank");
  };

  const handlePurchase = () => {
    window.open("https://xeryon.com/products/development-kits/", "_blank");
  };

  const handleFeedbackSubmit = () => {
    if (feedback.trim()) {
      submitFeedback.mutate(feedback);
    }
  };

  const cardClasses = isFullscreen
    ? "fixed inset-0 z-50 m-0 rounded-none overflow-auto bg-background"
    : "";

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
              <span
                className={`text-sm px-2 py-1 rounded-full ${
                  station.status === "available"
                    ? "bg-green-100 text-green-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
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
                  <CameraFeed stationId={station.id} rpiId={station.rpiId} />
                </div>
              </div>
              <div className="space-y-8">
                <AdvancedControls
                  station={station}
                  enabled={isMySession}
                  isConnected={wsConnection.connected}
                  onCommand={handleCommand}
                />
                {station.sessionStart && isMySession && (
                  <div>
                    <SessionTimer
                      startTime={station.sessionStart}
                      onTimeout={() => {
                        endSession.mutate();
                        setShowThankYouDialog(true);
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
                      setShowThankYouDialog(true);
                    }}
                    disabled={endSession.isPending}
                  >
                    End Session
                  </Button>
                ) : (
                  <Button className="w-full" disabled>
                    Station Occupied
                  </Button>
                )}
              </div>
            </div>
          ) : (
            // Overview layout - 50/50 split
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="aspect-video relative">
                  <CameraFeed stationId={station.id} rpiId={station.rpiId} />
                </div>
                <div className="aspect-video relative bg-muted rounded-lg overflow-hidden">
                  {station.previewImage ? (
                    <img
                      src={station.previewImage}
                      alt={`${station.name} preview`}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground">
                      No preview image available
                    </div>
                  )}
                </div>
              </div>
              {station.sessionStart && isMySession && (
                <div className="mb-4">
                  <SessionTimer
                    startTime={station.sessionStart}
                    onTimeout={() => {
                      endSession.mutate();
                      setShowThankYouDialog(true);
                    }}
                  />
                </div>
              )}
              <div className="space-y-4">
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
                      setShowThankYouDialog(true);
                    }}
                    disabled={endSession.isPending}
                  >
                    End Session
                  </Button>
                ) : (
                  <Button className="w-full" disabled>
                    Station Occupied
                  </Button>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showThankYouDialog} onOpenChange={setShowThankYouDialog}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Thank You for Using Our Demo Station!</DialogTitle>
            <DialogDescription className="pt-4">
              We hope you enjoyed experiencing our high-precision actuators. Would you like to learn more about our products or get in touch with us?
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-6">
            <div className="flex flex-col gap-4">
              <Button
                className="w-full bg-[#0079C1] hover:bg-[#006BA7] text-white transition-colors"
                onClick={handlePurchase}
              >
                <CreditCard className="h-4 w-4 mr-2" />
                Purchase Development Kit
              </Button>
              <Button variant="outline" className="w-full" onClick={handleContactUs}>
                <Mail className="h-4 w-4 mr-2" />
                Contact Us
              </Button>
            </div>

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
                onClick={handleFeedbackSubmit}
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