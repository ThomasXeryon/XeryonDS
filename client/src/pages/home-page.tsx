
import { Button } from "@/components/ui/button";
import { LogOut, LayoutDashboard } from "lucide-react";
import { useLocation } from "wouter";
import { ThemeToggle } from "@/components/theme-toggle";
import { useTheme } from "@/hooks/use-theme";
import { useAuth } from "@/hooks/use-auth";

export default function HomePage() {
  const { user, logoutMutation } = useAuth();
  const [, setLocation] = useLocation();
  const { theme } = useTheme();

  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container mx-auto px-4 h-16 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <img 
              src={theme === "dark" ? "/Xeryon-logo.png" : "/Xeryon-logo-v2.png"} 
              alt="Xeryon Logo" 
              className="h-8 object-contain cursor-pointer"
              onClick={() => setLocation("/")}
            />
            <h1 className="text-2xl font-bold hidden md:block">Remote Demo Station</h1>
          </div>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            {user?.isAdmin && (
              <Button 
                variant="ghost" 
                size="icon"
                onClick={() => setLocation("/admin")}
                className="hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <LayoutDashboard className="h-5 w-5" />
              </Button>
            )}
            <Button 
              variant="ghost" 
              size="icon"
              onClick={() => logoutMutation.mutate()}
              className="hover:bg-accent hover:text-accent-foreground transition-colors"
            >
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>
      <main className="container mx-auto px-4 py-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* This will be filled in with station cards */}
        </div>
      </main>
    </div>
  );
}
