import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const statusVariants = cva(
  "h-4 w-4 rounded-full relative transition-all duration-300 ease-in-out",
  {
    variants: {
      status: {
        available: "bg-emerald-500 scale-100",
        in_use: "bg-amber-500 scale-110",
        connecting: "bg-blue-500 scale-105",
      },
    },
    defaultVariants: {
      status: "available",
    },
  }
);

interface StatusIndicatorProps extends VariantProps<typeof statusVariants> {
  className?: string;
}

export { StatusIndicator as StationStatus };

export function StatusIndicator({ status, className }: StatusIndicatorProps) {
  return (
    <div className="relative flex items-center gap-2">
      <div className="relative">
        <span className={cn(statusVariants({ status }), className)} />
        <span
          className={cn(
            "absolute inset-0 rounded-full animate-ping opacity-75 transition-colors duration-300",
            status === "available" && "bg-emerald-500/50",
            status === "in_use" && "bg-amber-500/50",
            status === "connecting" && "bg-blue-500/50"
          )}
        />
        <span
          className={cn(
            "absolute -inset-1 rounded-full blur-sm transition-colors duration-300",
            status === "available" && "bg-emerald-500/30",
            status === "in_use" && "bg-amber-500/30",
            status === "connecting" && "bg-blue-500/30"
          )}
        />
      </div>
      <span className="text-sm font-medium transition-colors duration-300">
        {status === "in_use" ? "In Use" : status === "connecting" ? "Connecting" : "Available"}
      </span>
    </div>
  );
}