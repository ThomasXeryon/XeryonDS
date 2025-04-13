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
      {/* Step Controls with improved sizing and spacing */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <Label htmlFor="stepSize" className="text-sm font-medium whitespace-nowrap">Step Size:</Label>
          <div className="flex items-center gap-2">
            <Input
              id="stepSize"
              type="text"
              value={stepSize}
              onChange={handleStepSizeChange}
              className="w-24 h-9"
              disabled={!enabled || !isConnected}
            />
            <Select 
              value={stepUnit} 
              onValueChange={setStepUnit}
              disabled={!enabled || !isConnected}
            >
              <SelectTrigger className="h-9 w-20 text-sm">
                <SelectValue placeholder="Unit" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="mm">mm</SelectItem>
                <SelectItem value="µm">µm</SelectItem>
                <SelectItem value="nm">nm</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        
        {/* Control buttons with consistent height */}
        <div className="grid grid-cols-3 gap-3 mx-auto w-full">
          <Button
            variant="outline"
            className="w-full h-10"
            disabled={!enabled || !isConnected}
            onClick={() => handleCommand("move", "left")}
          >
            <MinusCircle className="h-5 w-5 mr-1" />
            Step
          </Button>
          <Button
            variant="default"
            className="w-full h-10 bg-white text-primary hover:bg-slate-100 border border-primary shadow-none"
            disabled={!enabled || !isConnected}
            onClick={() => handleCommand("home")}
          >
            <Home className="h-5 w-5 mr-1" />
            Home
          </Button>
          <Button
            variant="outline"
            className="w-full h-10"
            disabled={!enabled || !isConnected}
            onClick={() => handleCommand("move", "right")}
          >
            <PlusCircle className="h-5 w-5 mr-1" />
            Step
          </Button>
        </div>
      </div>

      {/* Scan Controls with consistent height */}
      <div className="grid grid-cols-3 gap-3 mx-auto w-full">
        <Button
          variant="outline"
          className="w-full h-10"
          disabled={!enabled || !isConnected}
          onClick={() => handleCommand("scan", "left")}
        >
          <MinusCircle className="h-5 w-5 mr-1" />
          Scan
        </Button>
        <Button
          variant="destructive"
          className="w-full h-10"
          disabled={!enabled || !isConnected}
          onClick={() => handleCommand("stop")}
        >
          <Square className="h-5 w-5 mr-1" />
          Stop
        </Button>
        <Button
          variant="outline"
          className="w-full h-10"
          disabled={!enabled || !isConnected}
          onClick={() => handleCommand("scan", "right")}
        >
          <PlusCircle className="h-5 w-5 mr-1" />
          Scan
        </Button>
      </div>

      {/* Speed Slider with improved spacing */}
      <div className="space-y-3 pt-1">
        <div className="flex justify-between items-center">
          <label className="text-sm font-medium">Speed (mm/s)</label>
          <span className="text-sm font-semibold">{speed[0]}</span>
        </div>
        <Slider
          value={speed}
          onValueChange={handleSpeedChange}
          max={1000}
          step={1}
          disabled={!enabled || !isConnected}
          className="py-1"
        />
      </div>

      {/* Demo Controls with consistent height */}
      <div className="grid grid-cols-2 gap-3 mx-auto w-full pt-1">
        <Button
          className="w-full h-10"
          variant={isDemoRunning ? "outline" : "default"}
          disabled={!enabled || !isConnected || isDemoRunning}
          onClick={() => {
            setIsDemoRunning(true);
            handleCommand("demo_start");
          }}
        >
          <Play className="h-5 w-5 mr-1" />
          Start Demo
        </Button>
        <Button
          className="w-full h-10"
          variant="outline"
          disabled={!enabled || !isConnected || !isDemoRunning}
          onClick={() => {
            setIsDemoRunning(false);
            handleCommand("demo_stop");
          }}
        >
          <StopCircle className="h-5 w-5 mr-1" />
          Stop Demo
        </Button>
      </div>
    </div>
  );
}