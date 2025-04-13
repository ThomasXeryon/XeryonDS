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

  // Effect for updating position data whenever currentPosition changes
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
  
  // Continuous data sampling effect with enhanced interpolation between points
  useEffect(() => {
    console.log('[PositionGraph] Setting up sampling interval with interpolation');
    
    // Set up an interval to continuously add data points
    const intervalId = setInterval(() => {
      const now = Date.now();
      
      // If we have a position stored in our ref, add it to the graph
      if (lastPositionRef.current !== null) {
        setPositionData(prevData => {
          // Only add a new point if we have data points
          if (prevData.length === 0) return prevData;
          
          // Get the last point we added
          const lastPoint = prevData[prevData.length - 1];
          
          // If the last point is too recent, don't add a new one yet
          if (now - lastPoint.time < sampleInterval * 0.8) return prevData;
          
          // Create a new data point with the current timestamp and latest position
          const newDataPoint = {
            time: now,
            position: lastPositionRef.current!
          };
          
          // Add the new point
          const updatedData = [...prevData, newDataPoint];
          
          // Filter out points older than our window size
          const cutoffTime = now - windowSize;
          const filteredData = updatedData.filter(point => point.time >= cutoffTime);
          
          // If we have at least 3 data points, we can start interpolating
          if (filteredData.length >= 3) {
            // Generate intermediate points for smoother plotting (every 50ms)
            const lastThreePoints = filteredData.slice(-3);
            const interpolatedData = [...filteredData];
            
            // Only interpolate if the points aren't already too close together
            const timeGap = lastThreePoints[2].time - lastThreePoints[1].time;
            if (timeGap > 300) { // Only interpolate for gaps larger than 300ms
              const numIntermediatePoints = Math.floor(timeGap / 50) - 1;
              
              for (let i = 1; i <= numIntermediatePoints; i++) {
                const t = i / (numIntermediatePoints + 1);
                const intermediateTime = lastThreePoints[1].time + t * (lastThreePoints[2].time - lastThreePoints[1].time);
                
                // Use quadratic interpolation for smoother curves
                const p0 = lastThreePoints[0].position;
                const p1 = lastThreePoints[1].position;
                const p2 = lastThreePoints[2].position;
                
                // Simple quadratic interpolation
                const a = (p0 - 2*p1 + p2) / 2;
                const b = (-3*p0 + 4*p1 - p2) / 2;
                const c = p0;
                
                const intermediatePosition = a*t*t + b*t + c;
                
                interpolatedData.push({
                  time: intermediateTime,
                  position: intermediatePosition
                });
              }
              
              // Sort data by time to ensure correct ordering
              interpolatedData.sort((a, b) => a.time - b.time);
            }
            
            return interpolatedData;
          }
          
          return filteredData;
        });
      }
    }, 30); // Reduced interval for more frequent updates
    
    return () => {
      console.log('[PositionGraph] Cleaning up sampling interval');
      clearInterval(intervalId);
    };
  }, [sampleInterval, windowSize]);

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
              type="monotone" // Changed back to monotone for smoother motion visualization
              dataKey="position" 
              stroke="#0373fc" 
              dot={false} 
              strokeWidth={1.5}
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