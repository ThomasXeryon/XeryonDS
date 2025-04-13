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

  // Store the most recent position value received
  useEffect(() => {
    if (currentPosition !== null) {
      console.log(`[PositionGraph] Current position updated: ${currentPosition}`);
      lastPositionRef.current = currentPosition;
    }
  }, [currentPosition]);

  // Main effect for continuous plotting - always runs to maintain data flow
  useEffect(() => {
    // Set up an interval to keep the graph moving and add new points
    const intervalId = setInterval(() => {
      const now = Date.now();
      
      setPositionData(prevData => {
        let updatedData = [...prevData];
        
        // If we have a position value, add it to the graph with the current timestamp
        if (lastPositionRef.current !== null) {
          // Add a new data point with current timestamp and latest position
          const newDataPoint = {
            time: now,
            position: lastPositionRef.current
          };
          
          // Add the new point - this ensures we're always plotting the current value
          // even if it hasn't changed
          updatedData.push(newDataPoint);
        }
        
        // Filter out points older than our window size to maintain the scrolling effect
        const cutoffTime = now - windowSize;
        const filteredData = updatedData.filter(point => point.time >= cutoffTime);
        
        // If we've filtered out all data points but we have a current position,
        // keep at least one point at the left edge of the visible area
        if (filteredData.length === 0 && lastPositionRef.current !== null) {
          return [{
            time: now - windowSize + 100,
            position: lastPositionRef.current
          }];
        }
        
        return filteredData;
      });
    }, 100); // Update every 100ms - frequent enough for smooth animation but not too resource-intensive
    
    return () => {
      clearInterval(intervalId);
    };
  }, [windowSize]);

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
              domain={[
                (dataMin: number) => {
                  const now = Date.now();
                  return now - windowSize;
                }, 
                (dataMax: number) => {
                  return Date.now();
                }
              ]}
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
              type="monotone" // Using monotone for scanning-friendly smoother diagonal lines
              dataKey="position" 
              stroke="#0373fc" 
              dot={false} // No dots, just the line
              strokeWidth={1.5}
              isAnimationActive={false}
              connectNulls={true}
              activeDot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}