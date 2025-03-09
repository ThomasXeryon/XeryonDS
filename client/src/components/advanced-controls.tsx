import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { MinusCircle, PlusCircle, Square, Play, StopCircle } from "lucide-react";
import { Station } from "@shared/schema";

interface AdvancedControlsProps {
  station: Station;
  enabled: boolean;
  isConnected: boolean;
  onCommand: (command: string, direction?: string) => void;
}

export function AdvancedControls({ station, enabled, isConnected, onCommand }: AdvancedControlsProps) {
  const [stepSize, setStepSize] = useState("1.0");
  const [speed, setSpeed] = useState([500]); // Default to middle of range
  const [isDemoRunning, setIsDemoRunning] = useState(false);

  const handleSpeedChange = (value: number[]) => {
    setSpeed(value);
    if (!enabled || !isConnected) return;
    onCommand("speed", value[0].toString());
  };

  return (
    <div className="space-y-6">
      {/* Step Controls */}
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!enabled || !isConnected}
          onClick={() => onCommand("step", "-" + stepSize)}
        >
          <MinusCircle className="h-4 w-4 mr-1" />
          Step
        </Button>
        <Input
          type="number"
          value={stepSize}
          onChange={(e) => setStepSize(e.target.value)}
          className="w-24"
          disabled={!enabled || !isConnected}
        />
        <Button
          variant="outline"
          size="sm"
          disabled={!enabled || !isConnected}
          onClick={() => onCommand("step", stepSize)}
        >
          <PlusCircle className="h-4 w-4 mr-1" />
          Step
        </Button>
      </div>

      {/* Scan Controls */}
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!enabled || !isConnected}
          onClick={() => onCommand("scan", "left")}
        >
          <MinusCircle className="h-4 w-4 mr-1" />
          Scan
        </Button>
        <Button
          variant="destructive"
          size="sm"
          disabled={!enabled || !isConnected}
          onClick={() => onCommand("stop")}
        >
          <Square className="h-4 w-4" />
          Stop
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!enabled || !isConnected}
          onClick={() => onCommand("scan", "right")}
        >
          <PlusCircle className="h-4 w-4 mr-1" />
          Scan
        </Button>
      </div>

      {/* Speed Slider */}
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <label className="font-medium">Speed (mm/s)</label>
          <span>{speed[0]}</span>
        </div>
        <Slider
          value={speed}
          onValueChange={handleSpeedChange}
          max={1000}
          step={1}
          disabled={!enabled || !isConnected}
        />
      </div>

      {/* Demo Controls */}
      <div className="flex gap-2">
        <Button
          className="flex-1"
          variant={isDemoRunning ? "outline" : "default"}
          disabled={!enabled || !isConnected || isDemoRunning}
          onClick={() => {
            setIsDemoRunning(true);
            onCommand("demo_start");
          }}
        >
          <Play className="h-4 w-4 mr-1" />
          Start Demo
        </Button>
        <Button
          className="flex-1"
          variant="outline"
          disabled={!enabled || !isConnected || !isDemoRunning}
          onClick={() => {
            setIsDemoRunning(false);
            onCommand("demo_stop");
          }}
        >
          <StopCircle className="h-4 w-4 mr-1" />
          Stop Demo
        </Button>
      </div>
    </div>
  );
}