import { useEffect, useState, useRef } from "react";
import { Card, CardContent } from "./ui/card";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from "recharts";

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
  
  useEffect(() => {
    // Update the last known position when we receive a valid position
    if (currentPosition !== null) {
      lastPositionRef.current = currentPosition;
    }
    
    // Set up an interval to continuously add data points
    const intervalId = setInterval(() => {
      const now = Date.now();
      
      // If we have a position, add it to the graph
      if (lastPositionRef.current !== null) {
        setPositionData(prevData => {
          // Create a new data point with the current timestamp and latest position
          const newDataPoint = {
            time: now,
            position: lastPositionRef.current!
          };
          
          // Add the new point
          const updatedData = [...prevData, newDataPoint];
          
          // Filter out points older than our window size
          const cutoffTime = now - windowSize;
          return updatedData.filter(point => point.time >= cutoffTime);
        });
      }
    }, sampleInterval);
    
    return () => clearInterval(intervalId);
  }, []);

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
              type="linear" // Changed from monotone to linear for less smoothing
              dataKey="position" 
              stroke="#0373fc" 
              dot={false} 
              strokeWidth={1.5} // Reduced stroke width
              isAnimationActive={false}
              connectNulls={true}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}