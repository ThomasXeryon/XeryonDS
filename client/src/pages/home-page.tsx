import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/hooks/use-auth";
import { Station } from "@shared/schema";
import { StationCard } from "@/components/station-card";
import { Button } from "@/components/ui/button";
import { LogOut, LayoutDashboard } from "lucide-react";
import { useLocation } from "wouter";
import { useTheme } from "@/hooks/use-theme";

export default function HomePage() {
  const { user, logoutMutation } = useAuth();
  const { theme } = useTheme();
  const [, setLocation] = useLocation();

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
              src={theme === "dark" ? "/correct/path/Xeryon-logo-dark.png" : "/Xeryon-logo-v2.png"} 
              alt="Xeryon Logo" 
              className="h-8 object-contain cursor-pointer"
              onClick={() => setLocation("/")}
            />
            <h1 className="text-2xl font-bold">Demo Stations</h1>
          </div>
          <div id="user-controls" className="flex items-center gap-4">
            <span>Welcome, {user?.username}</span>
            {user?.isAdmin && (
              <Button 
                id="admin-dashboard"
                variant="outline" 
                size="sm" 
                onClick={() => setLocation("/admin")}
                className="hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <LayoutDashboard className="h-4 w-4 mr-2" />
                Dashboard
              </Button>
            )}
            <ThemeToggle />
            <Button 
              variant="outline" 
              size="sm" 
              onClick={handleLogout}
              className="hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <main id="demo-stations" className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {stations?.map((station) => (
            <div key={station.id} className="station-card">
              <StationCard station={station} />
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}