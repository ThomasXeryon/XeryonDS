import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Station } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useLocation } from "wouter";
import { ArrowLeft, Plus, Loader2, Trash2, Settings, Upload } from "lucide-react";
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
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { StatusIndicator } from "@/components/station-status";
import { cn } from "@/lib/utils";
import { CameraFeed } from "@/components/camera-feed"; // Import CameraFeed

export default function StationsPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const [newStationName, setNewStationName] = useState("");
  const [rpiId, setRpiId] = useState("");
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [selectedStation, setSelectedStation] = useState<Station | null>(null);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);

  const { data: stations, isLoading } = useQuery<Station[]>({
    queryKey: ["/api/stations"],
  });

  const createStation = useMutation({
    mutationFn: async ({ name, rpiId }: { name: string; rpiId: string }) => {
      try {
        const res = await apiRequest("POST", "/api/admin/stations", { name, rpiId });

        if (!res.ok) {
          const errorData = await res.json().catch(() => ({}));
          throw new Error(errorData.message || `Failed to create station: ${res.status} ${res.statusText}`);
        }

        const station = await res.json();

        if (selectedImage) {
          const formData = new FormData();
          formData.append('image', selectedImage);
          formData.append('name', name); // Add name to formData in case it's needed

          const uploadRes = await fetch(`/api/admin/stations/${station.id}/image`, {
            method: 'POST',
            body: formData,
            credentials: 'include'
          });

          if (!uploadRes.ok) {
            console.warn("Image upload failed, but station was created");
          }
        }

        return station;
      } catch (error) {
        console.error("Station creation error:", error);
        throw error;
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      toast({
        title: "Station created",
        description: "New demo station has been added successfully",
      });
      setNewStationName("");
      setRpiId("");
      setSelectedImage(null);
      setIsAddDialogOpen(false);
    },
    onError: (error: any) => {
      toast({
        title: "Failed to create station",
        description: error.message || "An unexpected error occurred",
        variant: "destructive",
      });
    },
  });

  const updateStation = useMutation({
    mutationFn: async (station: Station) => {
      const res = await apiRequest("PATCH", `/api/admin/stations/${station.id}`, {
        name: station.name,
        rpiId: station.rpiId,
      });
      return await res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });
      toast({
        title: "Station updated",
        description: "Station details have been updated successfully",
      });
      setSelectedStation(null);
      setIsEditDialogOpen(false);
    },
    onError: (error: Error) => {
      toast({
        title: "Failed to update station",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const deleteStation = useMutation({
    mutationFn: async (id: number) => {
      await apiRequest("DELETE", `/api/admin/stations/${id}`);
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

  const uploadImage = useMutation({
    mutationFn: async ({ stationId, file }: { stationId: number; file: File }) => {
      const formData = new FormData();
      formData.append('image', file);

      const res = await fetch(`/api/admin/stations/${stationId}/image`, {
        method: 'POST',
        body: formData,
        credentials: 'include'
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.message || `Failed to upload image: ${res.status} ${res.statusText}`);
      }

      return await res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/stations"] });

      // Update the selectedStation with the new image URL if in edit dialog
      if (selectedStation && data.url) {
        setSelectedStation({
          ...selectedStation,
          previewImage: data.url
        });
      }

      toast({
        title: "Image uploaded",
        description: "Station preview image has been updated",
      });
    },
    onError: (error: any) => {
      toast({
        title: "Failed to upload image",
        description: error.message || "An unexpected error occurred",
        variant: "destructive",
      });
    },
  });

  const handleStationClick = (station: Station) => {
    setSelectedStation(station);
    setIsEditDialogOpen(true);
  };

  if (!user?.isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Card>
          <CardContent className="pt-6">
            <p>You don't have permission to access this page.</p>
            <Button className="mt-4" onClick={() => setLocation("/")}>
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
          <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-primary hover:bg-primary/90 transition-colors">
                <Plus className="h-4 w-4 mr-2" />
                Add Station
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add New Demo Station</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 pt-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Station Name</Label>
                  <Input
                    id="name"
                    placeholder="Station Name"
                    value={newStationName}
                    onChange={(e) => setNewStationName(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rpiId">RPi ID</Label>
                  <Input
                    id="rpiId"
                    placeholder="RPi ID (e.g., RPI1)"
                    value={rpiId}
                    onChange={(e) => setRpiId(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="preview">Preview Image</Label>
                  <div className="flex items-center gap-4">
                    <Input
                      id="preview"
                      type="file"
                      accept="image/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setSelectedImage(file);
                        }
                      }}
                    />
                    {selectedImage && (
                      <div className="text-sm text-muted-foreground">
                        {selectedImage.name}
                      </div>
                    )}
                  </div>
                </div>
                <Button
                  className="w-full bg-primary hover:bg-primary/90 transition-colors"
                  onClick={() => createStation.mutate({ name: newStationName, rpiId })}
                  disabled={createStation.isPending || !newStationName.trim() || !rpiId.trim()}
                >
                  {createStation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Plus className="h-4 w-4 mr-2" />
                  )}
                  Create Station
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {stations?.map((station) => (
            <Card
              key={station.id}
              className="hover:bg-accent/5 transition-colors group cursor-pointer"
              onClick={() => handleStationClick(station)}
            >
              <CardHeader>
                <CardTitle className="flex justify-between items-center">
                  <span>{station.name}</span>
                  <div className="flex items-center gap-2">
                    <label
                      className="cursor-pointer"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="file"
                        className="hidden"
                        accept="image/*"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                            uploadImage.mutate({ stationId: station.id, file });
                          }
                        }}
                      />
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 group-hover:opacity-100 hover:bg-accent hover:text-accent-foreground transition-colors"
                        title="Upload preview image"
                        disabled={uploadImage.isPending}
                      >
                        {uploadImage.isPending ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Upload className="h-4 w-4" />
                        )}
                      </Button>
                    </label>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 opacity-0 group-hover:opacity-100 hover:bg-destructive hover:text-destructive-foreground transition-all"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteStation.mutate(station.id);
                      }}
                      disabled={deleteStation.isPending}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {/* Add CameraFeed for live feed */}
                  <div className="aspect-video rounded-lg overflow-hidden bg-muted">
                    <CameraFeed rpiId={station.rpiId} />
                  </div>
                  {/* Keep previewImage as fallback or additional info */}
                  {station.previewImage && (
                    <div className="aspect-video rounded-lg overflow-hidden bg-muted">
                      <img
                        src={station.previewImage}
                        alt={`${station.name} preview`}
                        className="w-full h-full object-cover"
                      />
                    </div>
                  )}
                  <div className="flex items-center justify-between p-3 rounded-lg bg-accent/5 group-hover:bg-accent/10 transition-colors">
                    <span className="text-sm text-muted-foreground">Status</span>
                    <StatusIndicator
                      status={station.status as "available" | "in_use" | "connecting"}
                    />
                  </div>
                  {station.ipAddress && (
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">IP Address</span>
                      <span>{station.ipAddress}</span>
                    </div>
                  )}
                  {station.port && (
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Port</span>
                      <span>{station.port}</span>
                    </div>
                  )}
                  {station.currentUserId && (
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Current Session</span>
                      <span>Active</span>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>

      {/* Edit Station Dialog */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Station</DialogTitle>
          </DialogHeader>
          {selectedStation && (
            <div className="space-y-4 pt-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">Station Name</Label>
                <Input
                  id="edit-name"
                  placeholder="Station Name"
                  value={selectedStation.name}
                  onChange={(e) => setSelectedStation({ ...selectedStation, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-rpiId">RPi ID</Label>
                <Input
                  id="edit-rpiId"
                  placeholder="RPi ID (e.g., RPI1)"
                  value={selectedStation.rpiId}
                  onChange={(e) => setSelectedStation({ ...selectedStation, rpiId: e.target.value })}
                />
              </div>
              <Button
                className="w-full bg-primary hover:bg-primary/90 transition-colors"
                onClick={() => updateStation.mutate(selectedStation)}
                disabled={updateStation.isPending}
              >
                {updateStation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Settings className="h-4 w-4 mr-2" />
                )}
                Update Station
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}