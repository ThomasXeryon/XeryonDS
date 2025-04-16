import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { MinusCircle, PlusCircle, Square, Play, StopCircle, Home } from "lucide-react";
import { Station } from "@shared/schema";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

interface AdvancedControlsProps {
  station: Station;
  enabled: boolean;
  isConnected: boolean;
  onCommand: (command: string, direction?: string, options?: { 
    stepSize?: number; 
    stepUnit?: string;
    acce?: number;
    dece?: number;
  }) => void;
}

export function AdvancedControls({ station, enabled, isConnected, onCommand }: AdvancedControlsProps) {
  const [stepSize, setStepSize] = useState("1.0");
  const [stepUnit, setStepUnit] = useState("mm");
  const [speed, setSpeed] = useState([500]); // Default to middle of range
  const [acceleration, setAcceleration] = useState([32750]); // Default to middle of ACCE range (0-65500)
  const [deceleration, setDeceleration] = useState([32750]); // Default to middle of DECE range (0-65500)
  const [isDemoRunning, setIsDemoRunning] = useState(false);
  
  // Store initial values to avoid sending unnecessary commands
  const initialAcceleration = 32750;
  const initialDeceleration = 32750;

  // Handle speed changes
  const handleSpeedChange = (value: number[]) => {
    setSpeed(value);
  };

  const handleSpeedCommit = () => {
    if (!enabled || !isConnected) return;
    onCommand("speed", speed[0].toString());
  };
  
  // Handle acceleration changes
  const handleAccelerationChange = (value: number[]) => {
    setAcceleration(value);
  };

  const handleAccelerationCommit = () => {
    if (!enabled || !isConnected) return;
    onCommand("acceleration", acceleration[0].toString());
  };
  
  // Handle deceleration changes
  const handleDecelerationChange = (value: number[]) => {
    setDeceleration(value);
  };

  const handleDecelerationCommit = () => {
    if (!enabled || !isConnected) return;
    onCommand("deceleration", deceleration[0].toString());
  };
  
  // Handle step size input change
  const handleStepSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Only allow numeric values with up to one decimal point
    if (/^\d*\.?\d*$/.test(value)) {
      setStepSize(value);
    }
  };
  
  // Enhanced command handling with step size, unit, and motion parameters
  const handleCommand = (command: string, direction?: string) => {
    if (!enabled || !isConnected) return;
    
    // Include step size and unit in the command if it's a step or move command
    if (command === "move" || command === "step") {
      onCommand(command, direction, {
        stepSize: parseFloat(stepSize) || 1.0,
        stepUnit,
        acce: acceleration[0],
        dece: deceleration[0]
      });
    } else if (command === "scan") {
      onCommand(command, direction, {
        acce: acceleration[0],
        dece: deceleration[0]
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
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
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
        
        {/* Control buttons with consistent height and responsive layout */}
        <div className="grid grid-cols-3 gap-2 md:gap-3 mx-auto w-full">
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

      {/* Scan Controls with consistent height and responsive layout */}
      <div className="grid grid-cols-3 gap-2 md:gap-3 mx-auto w-full">
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
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1">
          <label className="text-sm font-medium">Speed (mm/s)</label>
          <span className="text-sm font-semibold">{speed[0]}</span>
        </div>
        <Slider
          value={speed}
          onValueChange={handleSpeedChange}
          onValueCommit={handleSpeedCommit}
          min={1}
          max={1000}
          step={10}
          disabled={!enabled || !isConnected}
          className="py-1"
        />
      </div>

      {/* Advanced Motion Control Section */}
      <Accordion type="single" collapsible className="w-full">
        <AccordionItem value="motion-control">
          <AccordionTrigger className="text-sm font-medium">Advanced Motion Control</AccordionTrigger>
          <AccordionContent>
            <div className="space-y-4 pt-2">
              {/* Acceleration Slider */}
              <div className="space-y-2">
                <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1">
                  <label className="text-sm font-medium">Acceleration</label>
                  <span className="text-sm font-semibold">{acceleration[0]}</span>
                </div>
                <Slider
                  value={acceleration}
                  onValueChange={handleAccelerationChange}
                  onValueCommit={handleAccelerationCommit}
                  min={1}
                  max={65500}
                  step={10}
                  disabled={!enabled || !isConnected}
                  className="py-1"
                />
              </div>
              
              {/* Deceleration Slider */}
              <div className="space-y-2">
                <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-1">
                  <label className="text-sm font-medium">Deceleration</label>
                  <span className="text-sm font-semibold">{deceleration[0]}</span>
                </div>
                <Slider
                  value={deceleration}
                  onValueChange={handleDecelerationChange}
                  onValueCommit={handleDecelerationCommit}
                  min={1}
                  max={65500}
                  step={10}
                  disabled={!enabled || !isConnected}
                  className="py-1"
                />
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
      
      {/* Demo Controls with consistent height and responsive layout */}
      <div className="grid grid-cols-2 gap-2 md:gap-3 mx-auto w-full pt-3">
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