
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { LogOut, LayoutDashboard } from "lucide-react";
import { useLocation } from "wouter";
import { useTheme } from "@/hooks/use-theme";
import { ThemeToggle } from "@/components/theme-toggle";

export default function HomePage() {
  const { user, logoutMutation } = useAuth();
  const [, setLocation] = useLocation();
  const { theme } = useTheme();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img 
              src={theme === "dark" ? "/Xeryon-logo.png" : "/Xeryon-logo-v2.png"} 
              alt="Xeryon Logo" 
              className="h-8 object-contain cursor-pointer"
              onClick={() => setLocation("/")}
            />
            <h1 className="text-xl font-semibold hidden sm:inline-block">Remote Demo Station</h1>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {user?.isAdmin && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setLocation("/admin")}
              >
                <LayoutDashboard className="h-4 w-4 mr-2" />
                Admin
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={() => logoutMutation.mutate()}
            >
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto px-4 py-6">
        <div className="grid md:grid-cols-2 gap-6">
          <div>
            <h2 className="text-2xl font-bold mb-4">Welcome, {user?.name || "User"}!</h2>
            <p className="text-muted-foreground mb-6">
              This platform allows you to remotely control and monitor Xeryon demo stations.
              Select a station below to begin.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
