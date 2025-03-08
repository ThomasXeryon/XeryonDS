import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useQuery, useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import { useLocation } from "wouter";
import { ArrowLeft, Loader2 } from "lucide-react";

// Define the Settings interface
interface Settings {
  rpiHost?: string;
  rpiPort?: number;
  rpiUsername?: string;
  rpiPassword?: string;
}

const formSchema = z.object({
  rpiHost: z.string().min(1, "Host is required"),
  rpiPort: z.string().regex(/^\d+$/, "Port must be a number"),
  rpiUsername: z.string().min(1, "Username is required"),
  rpiPassword: z.string().min(1, "Password is required"),
});

export default function SettingsPage() {
  const { user } = useAuth();
  const [, setLocation] = useLocation();

  const { data: settings, isLoading } = useQuery<Settings>({
    queryKey: ["/api/admin/settings"],
  });

  const mutation = useMutation({
    mutationFn: async (values: z.infer<typeof formSchema>) =>
      await apiRequest("PATCH", "/api/admin/settings", values),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/admin/settings"] });
    },
  });

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      rpiHost: settings?.rpiHost || "",
      rpiPort: settings?.rpiPort?.toString() || "22",
      rpiUsername: settings?.rpiUsername || "",
      rpiPassword: settings?.rpiPassword || "",
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

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin" />
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
              onClick={() => setLocation("/admin")}
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <h1 className="text-2xl font-bold">Settings</h1>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8">
        <Card>
          <CardHeader>
            <CardTitle>RPi Connection Settings</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form
                onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
                className="space-y-6"
              >
                <FormField
                  control={form.control}
                  name="rpiHost"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>RPi Host</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., 192.168.1.100" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="rpiPort"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>RPi Port</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., 22" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="rpiUsername"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>RPi Username</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., pi" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="rpiPassword"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>RPi Password</FormLabel>
                      <FormControl>
                        <Input type="password" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button
                  type="submit"
                  disabled={mutation.isPending}
                  className="w-full"
                >
                  {mutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : null}
                  Save Settings
                </Button>
              </form>
            </Form>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}