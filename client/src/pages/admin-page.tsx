import { useAuth } from "@/hooks/use-auth";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Station, SessionLog, User, Feedback } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useLocation } from "wouter";
import { Settings, Users, Activity, PlusCircle, Loader2, Home, MessageSquare } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export default function AdminPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [newStationName, setNewStationName] = useState("");
  const [ipAddress, setIpAddress] = useState("");
  const [port, setPort] = useState("");
  const [secretKey, setSecretKey] = useState("");

  const { data: stations } = useQuery<Station[]>({
    queryKey: ["/api/stations"],
  });

  const { data: sessionLogs } = useQuery<SessionLog[]>({
    queryKey: ["/api/admin/session-logs"],
  });

  const { data: users } = useQuery<User[]>({
    queryKey: ["/api/admin/users"],
  });

  const { data: feedback } = useQuery<Feedback[]>({
    queryKey: ["/api/admin/feedback"],
  });

  const createStation = useMutation({
    mutationFn: async ({ name, ipAddress, port, secretKey }: { name: string; ipAddress: string; port: string; secretKey: string }) => {
      const res = await apiRequest("POST", "/api/admin/stations", { name, ipAddress, port, secretKey });
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      toast({
        title: "Station created",
        description: "New demo station has been added successfully",
      });
      setNewStationName("");
      setIpAddress("");
      setPort("");
      setSecretKey("");
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to create station",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  if (!user?.isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Card>
          <CardContent className="pt-6">
            <p>You don't have permission to access this page.</p>
            <Button
              className="mt-4"
              onClick={() => setLocation("/")}
            >
              Return to Home
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img
              src="/Xeryon-logo-v2.png"
              alt="Xeryon Logo"
              className="h-8 object-contain cursor-pointer"
              onClick={() => setLocation("/")}
            />
            <h1 className="text-2xl font-bold">Admin Dashboard</h1>
          </div>
          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              onClick={() => setLocation("/")}
              className="hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <Home className="h-4 w-4 mr-2" />
              Back to Home
            </Button>
            
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/stations")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                <span>Stations</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stations?.length || 0}</div>
              <p className="text-sm text-muted-foreground">Active Stations</p>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/users")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                <span>Users</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{users?.length || 0}</div>
              <p className="text-sm text-muted-foreground">Registered Users</p>
            </CardContent>
          </Card>

          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/analytics")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                <span>Analytics</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{sessionLogs?.length || 0}</div>
              <p className="text-sm text-muted-foreground">Total Sessions</p>
            </CardContent>
          </Card>
          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/feedback")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5" />
                <span>Feedback</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{feedback?.length || 0}</div>
              <p className="text-sm text-muted-foreground">User Submissions</p>
            </CardContent>
          </Card>
          <Card className="hover:bg-accent/5 transition-colors cursor-pointer" onClick={() => setLocation("/admin/settings")}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                <span>Settings</span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Configure connection parameters</p>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}