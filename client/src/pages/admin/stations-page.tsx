import { useQuery, useMutation } from "@tanstack/react-query";
import { Station } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useLocation } from "wouter";
import { ArrowLeft, Plus, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { apiRequest, queryClient } from "@/lib/queryClient";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
} from "@/components/ui/dialog";
import { useState, useEffect } from "react";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { insertStationSchema } from "@shared/schema";
import type { z } from "zod";

type StationFormValues = z.infer<typeof insertStationSchema>;

export default function StationsPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const form = useForm<StationFormValues>({
    resolver: zodResolver(insertStationSchema),
    defaultValues: {
      name: "",
      description: "",
      rpiHost: "",
      rpiPort: 8080,
      rpiAuthToken: "",
    },
  });

  const { data: stations, isLoading } = useQuery<Station[]>({
    queryKey: ["/api/stations"],
  });

  const createStation = useMutation({
    mutationFn: async (values: StationFormValues) => {
      const res = await apiRequest("POST", "/api/admin/stations", values);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      toast({
        title: "Station created",
        description: "New demo station has been added successfully",
      });
      setIsDialogOpen(false);
      form.reset();
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to create station",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const deleteStation = useMutation({
    mutationFn: async (id: number) => {
      const res = await apiRequest("DELETE", `/api/admin/stations/${id}`);
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      toast({
        title: "Station removed",
        description: "The demo station has been removed successfully",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to remove station",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "station_update") {
        queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      }
    };

    return () => ws.close();
  }, []);

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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button
              variant="ghost"
              size="icon"
              className="hover:bg-accent hover:text-accent-foreground transition-colors"
              onClick={() => setLocation("/admin")}
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-2xl font-bold">Manage Stations</h1>
          </div>
          <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-primary hover:bg-primary/90 transition-colors">
                <Plus className="h-4 w-4 mr-2" />
                Add Station
              </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-[425px]">
              <DialogHeader>
                <DialogTitle>Add New Demo Station</DialogTitle>
                <DialogDescription>
                  Configure the connection details for the Raspberry Pi-controlled demo station.
                </DialogDescription>
              </DialogHeader>
              <Form {...form}>
                <form onSubmit={form.handleSubmit((data) => createStation.mutate(data))} className="space-y-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Station Name</FormLabel>
                        <FormControl>
                          <Input placeholder="Demo Station 1" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Description</FormLabel>
                        <FormControl>
                          <Input placeholder="Main demo station for XY actuator" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="rpiHost"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>RPi Host</FormLabel>
                        <FormControl>
                          <Input placeholder="192.168.1.100 or hostname" {...field} />
                        </FormControl>
                        <FormDescription>
                          IP address or hostname of the Raspberry Pi
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="rpiPort"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>WebSocket Port</FormLabel>
                        <FormControl>
                          <Input 
                            type="number" 
                            placeholder="8080"
                            {...field}
                            onChange={(e) => field.onChange(parseInt(e.target.value))}
                          />
                        </FormControl>
                        <FormDescription>
                          Port number for the WebSocket server on the RPi
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="rpiAuthToken"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Authentication Token</FormLabel>
                        <FormControl>
                          <Input type="password" placeholder="Secret token" {...field} />
                        </FormControl>
                        <FormDescription>
                          Authentication token for secure communication
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <Button 
                    type="submit" 
                    className="w-full bg-primary hover:bg-primary/90 transition-colors"
                    disabled={createStation.isPending}
                  >
                    {createStation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <Plus className="h-4 w-4 mr-2" />
                    )}
                    Create Station
                  </Button>
                </form>
              </Form>
            </DialogContent>
          </Dialog>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {stations?.map((station) => (
            <Card key={station.id} className="hover:bg-accent/5 transition-colors group">
              <CardHeader>
                <CardTitle className="flex justify-between items-center">
                  <span>{station.name}</span>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 opacity-0 group-hover:opacity-100 hover:bg-destructive hover:text-destructive-foreground transition-all"
                      onClick={() => deleteStation.mutate(station.id)}
                      disabled={deleteStation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span>Status</span>
                    <span className={`px-2 py-0.5 rounded-full ${
                      station.status === "available"
                        ? "bg-green-100 text-green-700"
                        : "bg-yellow-100 text-yellow-700"
                    }`}>
                      {station.status === "available" ? "Available" : "In Use"}
                    </span>
                  </div>
                  {station.currentUserId && (
                    <div className="flex justify-between text-sm">
                      <span>Current Session</span>
                      <span>Active</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}