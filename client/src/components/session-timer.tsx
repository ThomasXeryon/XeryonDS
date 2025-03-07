import { useEffect, useState } from "react";
import { Progress } from "@/components/ui/progress";

const SESSION_DURATION = 5 * 60; // 5 minutes in seconds

export function SessionTimer({ startTime, onTimeout }: { startTime: Date; onTimeout: () => void }) {
  const [timeLeft, setTimeLeft] = useState(SESSION_DURATION);

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - new Date(startTime).getTime()) / 1000);
      const remaining = Math.max(0, SESSION_DURATION - elapsed);
      setTimeLeft(remaining);

      if (remaining === 0) {
        clearInterval(interval);
        onTimeout(); // Trigger session end when time is up
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [startTime, onTimeout]);

  const minutes = Math.floor(timeLeft / 60);
  const seconds = timeLeft % 60;
  const progress = (timeLeft / SESSION_DURATION) * 100;

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span>Session Time Remaining</span>
        <span className="font-semibold text-foreground">
          {minutes.toString().padStart(2, "0")}:
          {seconds.toString().padStart(2, "0")}
        </span>
      </div>
      <Progress value={progress} />
    </div>
  );
}