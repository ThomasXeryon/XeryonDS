import { useEffect, useState, useRef } from "react";
import { Card, CardContent } from "./ui/card";
import { 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  CartesianGrid, 
  ReferenceLine 
} from "recharts";
import { curveCardinal } from "d3-shape";

interface PositionGraphProps {
  rpiId: string;
  currentPosition: number | null;
}

interface PositionDataPoint {
  time: number;
  position: number;
}

export function PositionGraph({ rpiId, currentPosition }: PositionGraphProps) {
  const [positionData, setPositionData] = useState<PositionDataPoint[]>([]);
  const lastPositionRef = useRef<number | null>(null);
  
  // Window size in milliseconds (10 seconds)
  const windowSize = 10000;
  // Sampling interval (add points every 100ms for a continuous graph)
  const sampleInterval = 100;
  
  // Log for debugging
  useEffect(() => {
    console.log(`[PositionGraph] Current position received: ${currentPosition}`);
  }, [currentPosition]);

  // Direct effect for updating position data whenever currentPosition changes
  // No interpolation, no smoothing, just raw data plotting
  useEffect(() => {
    // Only proceed if there's a valid position value
    if (currentPosition !== null) {
      console.log(`[PositionGraph] Adding position to graph: ${currentPosition}`);
      
      // Update the reference to the latest position value
      lastPositionRef.current = currentPosition;
      
      // Add a new data point immediately when position changes
      const now = Date.now();
      
      setPositionData(prevData => {
        // Create a new data point with the current timestamp and position
        const newDataPoint = {
          time: now,
          position: currentPosition
        };
        
        // Add the new point
        const updatedData = [...prevData, newDataPoint];
        
        // Filter out points older than our window size
        const cutoffTime = now - windowSize;
        const filtered = updatedData.filter(point => point.time >= cutoffTime);
        
        console.log(`[PositionGraph] Data points in chart: ${filtered.length}`);
        return filtered;
      });
    }
  }, [currentPosition, windowSize]);
  
  // No continuous data sampling - only plot the exact values as they arrive
  // Only the window size management is kept to maintain the 10-second view

  // Format time for tooltip
  const formatTime = (time: number) => {
    const date = new Date(time);
    return `${date.getMinutes()}:${date.getSeconds().toString().padStart(2, '0')}.${date.getMilliseconds().toString().padStart(3, '0')}`;
  };

  // If we don't have any data yet, show a placeholder message
  if (positionData.length === 0) {
    return (
      <Card className="w-full h-[500px] mb-4 bg-slate-50">
        <CardContent className="flex justify-center items-center h-full">
          <p className="text-gray-500">Move the actuator to see position data</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full h-[500px] mb-4 bg-slate-50">
      <CardContent className="p-2 h-full">
        <div className="text-sm font-medium mb-2 text-center">
          Position History for {rpiId} ({positionData.length > 0 ? `${positionData[positionData.length - 1].position.toFixed(3)} mm` : 'N/A'})
        </div>
        <ResponsiveContainer width="100%" height="90%">
          <LineChart data={positionData}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.6} />
            <XAxis 
              dataKey="time" 
              scale="time" 
              type="number"
              domain={['dataMin', 'dataMax']}
              tick={false}
              tickLine={false}
            />
            <YAxis 
              domain={['dataMin - 0.05', 'dataMax + 0.05']} 
              tickCount={10}
              tickFormatter={(value) => `${value.toFixed(3)}`}
              width={50}
            />
            {/* Add reference line for current position */}
            {lastPositionRef.current !== null && (
              <ReferenceLine 
                y={lastPositionRef.current} 
                stroke="#ff5500" 
                strokeDasharray="3 3" 
                label={{
                  value: `${lastPositionRef.current.toFixed(3)} mm`,
                  position: 'insideRight',
                  fill: '#ff5500',
                  fontSize: 10
                }}
              />
            )}
            <Tooltip 
              labelFormatter={(value) => `Time: ${formatTime(value as number)}`}
              formatter={(value: any) => [`${parseFloat(value).toFixed(3)} mm`, 'Position']}
              contentStyle={{ backgroundColor: 'rgba(255, 255, 255, 0.9)', borderRadius: '4px' }}
            />
            <Line 
              type="stepAfter" // Using stepAfter to clearly show the discrete nature of the data
              dataKey="position" 
              stroke="#0373fc" 
              dot={{ r: 2 }} // Small dots for each data point
              strokeWidth={1}
              isAnimationActive={false}
              connectNulls={true}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}