import { useQuery, useMutation } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { Station } from "@shared/schema";
import { StationCard } from "@/components/station-card";
import { Button } from "@/components/ui/button";
import { LogOut } from "lucide-react";
import { queryClient } from "@/lib/queryClient";

export default function HomePage() {
  const { user, logoutMutation } = useAuth();

  const { data: stations } = useQuery<Station[]>({
    queryKey: ["/api/stations"],
  });

  const handleLogout = async () => {
    await logoutMutation.mutateAsync();
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img 
              src="/attached_assets/Xeryon-logo-v2.webp" 
              alt="Xeryon Logo" 
              className="h-8 object-contain"
            />
            <h1 className="text-2xl font-bold">Demo Stations</h1>
          </div>
          <div className="flex items-center gap-4">
            <span>Welcome, {user?.username}</span>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {stations?.map((station) => (
            <StationCard key={station.id} station={station} />
          ))}
        </div>
      </main>
    </div>
  );
}