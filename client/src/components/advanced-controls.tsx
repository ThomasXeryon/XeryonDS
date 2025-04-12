import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { MinusCircle, PlusCircle, Square, Play, StopCircle, Home } from "lucide-react";
import { Station } from "@shared/schema";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";

interface AdvancedControlsProps {
  station: Station;
  enabled: boolean;
  isConnected: boolean;
  onCommand: (command: string, direction?: string, options?: { stepSize?: number; stepUnit?: string }) => void;
}

export function AdvancedControls({ station, enabled, isConnected, onCommand }: AdvancedControlsProps) {
  const [stepSize, setStepSize] = useState("1.0");
  const [stepUnit, setStepUnit] = useState("mm");
  const [speed, setSpeed] = useState([500]); // Default to middle of range
  const [isDemoRunning, setIsDemoRunning] = useState(false);

  const handleSpeedChange = (value: number[]) => {
    setSpeed(value);
    if (!enabled || !isConnected) return;
    onCommand("speed", value[0].toString());
  };
  
  // Handle step size input change
  const handleStepSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Only allow numeric values with up to one decimal point
    if (/^\d*\.?\d*$/.test(value)) {
      setStepSize(value);
    }
  };
  
  // Enhanced command handling with step size and unit
  const handleCommand = (command: string, direction?: string) => {
    if (!enabled || !isConnected) return;
    
    // Include step size and unit in the command if it's a step or move command
    if (command === "move" || command === "step") {
      onCommand(command, direction, {
        stepSize: parseFloat(stepSize) || 1.0,
        stepUnit
      });
    } else {
      onCommand(command, direction);
    }
  };

  // Get rpiId from station object
  const rpiId = station?.rpiId;
  if (!rpiId && enabled) {
    console.error("[AdvancedControls] No RPi ID available");
    return null;
  }

  return (
    <div className="space-y-6">
      {/* Step Controls */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Label htmlFor="stepSize" className="text-xs whitespace-nowrap">Step Size:</Label>
          <div className="flex items-center gap-2">
            <Input
              id="stepSize"
              type="text"
              value={stepSize}
              onChange={handleStepSizeChange}
              className="w-20 h-8"
              disabled={!enabled || !isConnected}
            />
            <Select 
              value={stepUnit} 
              onValueChange={setStepUnit}
              disabled={!enabled || !isConnected}
            >
              <SelectTrigger className="h-8 w-16 text-xs">
                <SelectValue placeholder="Unit" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="mm">mm</SelectItem>
                <SelectItem value="µm">µm</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2 mx-auto w-full max-w-xs">
          <Button
            variant="outline"
            size="sm"
            className="w-full h-9"
            disabled={!enabled || !isConnected}
            onClick={() => handleCommand("move", "left")}
          >
            <MinusCircle className="h-4 w-4 mr-1" />
            Step
          </Button>
          <Button
            variant="default"
            size="sm"
            className="w-full h-9 bg-white text-primary hover:bg-slate-100 border border-primary shadow-none"
            disabled={!enabled || !isConnected}
            onClick={() => handleCommand("home")}
          >
            <Home className="h-4 w-4 mr-1" />
            Home
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="w-full h-9"
            disabled={!enabled || !isConnected}
            onClick={() => handleCommand("move", "right")}
          >
            <PlusCircle className="h-4 w-4 mr-1" />
            Step
          </Button>
        </div>
      </div>

      {/* Scan Controls */}
      <div className="grid grid-cols-3 gap-2 mx-auto w-full max-w-xs">
        <Button
          variant="outline"
          size="sm"
          className="w-full h-9"
          disabled={!enabled || !isConnected}
          onClick={() => handleCommand("scan", "left")}
        >
          <MinusCircle className="h-4 w-4 mr-1" />
          Scan
        </Button>
        <Button
          variant="destructive"
          size="sm"
          className="w-full h-9"
          disabled={!enabled || !isConnected}
          onClick={() => handleCommand("stop")}
        >
          <Square className="h-4 w-4 mr-1" />
          Stop
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="w-full h-9"
          disabled={!enabled || !isConnected}
          onClick={() => handleCommand("scan", "right")}
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
      <div className="grid grid-cols-2 gap-2 mx-auto w-full max-w-xs">
        <Button
          className="w-full h-9"
          variant={isDemoRunning ? "outline" : "default"}
          disabled={!enabled || !isConnected || isDemoRunning}
          onClick={() => {
            setIsDemoRunning(true);
            handleCommand("demo_start");
          }}
        >
          <Play className="h-4 w-4 mr-1" />
          Start Demo
        </Button>
        <Button
          className="w-full h-9"
          variant="outline"
          disabled={!enabled || !isConnected || !isDemoRunning}
          onClick={() => {
            setIsDemoRunning(false);
            handleCommand("demo_stop");
          }}
        >
          <StopCircle className="h-4 w-4 mr-1" />
          Stop Demo
        </Button>
      </div>
    </div>
  );
}