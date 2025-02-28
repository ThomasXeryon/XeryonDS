import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const statusVariants = cva(
  "h-3 w-3 rounded-full relative",
  {
    variants: {
      status: {
        available: "bg-green-500",
        in_use: "bg-yellow-500",
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
    <div className="relative flex items-center">
      <span className={cn(statusVariants({ status }), className)}>
        <span className={cn(
          "absolute inset-0 rounded-full animate-ping",
          status === "available" && "bg-green-500/50",
          status === "in_use" && "bg-yellow-500/50",
          status === "connecting" && "bg-blue-500/50"
        )} />
      </span>
      <span className="ml-2 text-sm capitalize">
        {status === "in_use" ? "In Use" : status}
      </span>
    </div>
  );
}
