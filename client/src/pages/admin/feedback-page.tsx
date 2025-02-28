import { useQuery } from "@tanstack/react-query";
import { Feedback } from "@shared/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useLocation } from "wouter";
import { ArrowLeft, MessageCircle, Bug, CheckCircle2, Clock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { format } from "date-fns";

export default function FeedbackPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation();

  const { data: feedbackItems, isLoading } = useQuery<Feedback[]>({
    queryKey: ["/api/admin/feedback"],
    refetchInterval: 30000, // Refresh every 30 seconds
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
            <Button
              variant="ghost"
              size="icon"
              className="hover:bg-accent hover:text-accent-foreground transition-colors"
              onClick={() => setLocation("/admin")}
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-2xl font-bold">Feedback & Bug Reports</h1>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <div className="grid grid-cols-1 gap-6">
          {feedbackItems?.map((item) => (
            <Card key={item.id} className="hover:bg-accent/5 transition-colors">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    {item.type === 'feedback' ? (
                      <MessageCircle className="h-5 w-5 text-blue-500" />
                    ) : (
                      <Bug className="h-5 w-5 text-red-500" />
                    )}
                    <span className="capitalize">{item.type}</span>
                  </div>
                  <div className="flex items-center gap-2 text-sm">
                    {item.status === 'pending' ? (
                      <Clock className="h-4 w-4 text-yellow-500" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 text-green-500" />
                    )}
                    <span className="capitalize">{item.status}</span>
                  </div>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground mb-4">{item.message}</p>
                <div className="text-xs text-muted-foreground">
                  Submitted on {format(new Date(item.createdAt), 'PPpp')}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}