import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const statusVariants = cva(
  "h-3 w-3 rounded-full relative",
  {
    variants: {
      status: {
        available: "bg-emerald-500",
        in_use: "bg-amber-500",
        connecting: "bg-blue-500",
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

export function StatusIndicator({ status, className }: StatusIndicatorProps) {
  return (
    <div className="relative flex items-center gap-2">
      <div className="relative">
        <span className={cn(statusVariants({ status }), className)} />
        <span
          className={cn(
            "absolute inset-0 rounded-full animate-ping opacity-75",
            status === "available" && "bg-emerald-500",
            status === "in_use" && "bg-amber-500",
            status === "connecting" && "bg-blue-500"
          )}
        />
      </div>
      <span className="text-sm font-medium">
        {status === "in_use" ? "In Use" : status === "connecting" ? "Connecting" : "Available"}
      </span>
    </div>
  );
}