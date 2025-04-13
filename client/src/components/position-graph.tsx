import { useEffect, useState } from "react";
import { Card, CardContent } from "./ui/card";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

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
  const maxDataPoints = 100; // Maximum number of data points to display
  
  useEffect(() => {
    // Only add data points when we have a valid position
    if (currentPosition !== null) {
      setPositionData(prevData => {
        // Create a new data point with the current timestamp and position
        const newDataPoint = {
          time: Date.now(),
          position: currentPosition
        };
        
        // Add the new point and limit the size of the array
        const updatedData = [...prevData, newDataPoint];
        if (updatedData.length > maxDataPoints) {
          return updatedData.slice(-maxDataPoints);
        }
        return updatedData;
      });
    }
  }, [currentPosition]);

  // Format time for tooltip
  const formatTime = (time: number) => {
    const date = new Date(time);
    return `${date.getMinutes()}:${date.getSeconds().toString().padStart(2, '0')}.${date.getMilliseconds().toString().padStart(3, '0')}`;
  };

  // If we don't have any data yet, show a placeholder message
  if (positionData.length === 0) {
    return (
      <Card className="w-full h-[200px] mb-4 bg-slate-50">
        <CardContent className="flex justify-center items-center h-full">
          <p className="text-gray-500">Move the actuator to see position data</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full h-[200px] mb-4 bg-slate-50">
      <CardContent className="p-2 h-full">
        <div className="text-xs font-medium mb-1 text-center">
          Position History for {rpiId} ({positionData.length > 0 ? `${positionData[positionData.length - 1].position.toFixed(3)} mm` : 'N/A'})
        </div>
        <ResponsiveContainer width="100%" height="85%">
          <LineChart data={positionData}>
            <XAxis 
              dataKey="time" 
              scale="time" 
              type="number"
              domain={['dataMin', 'dataMax']}
              tick={false}
              tickLine={false}
            />
            <YAxis 
              domain={[0, 15]} 
              ticks={[0, 5, 10, 15]}
              tickFormatter={(value) => `${value}`}
              width={25}
            />
            <Tooltip 
              labelFormatter={(value) => `Time: ${formatTime(value as number)}`}
              formatter={(value: any) => [`${parseFloat(value).toFixed(3)} mm`, 'Position']}
            />
            <Line 
              type="monotone" 
              dataKey="position" 
              stroke="#0373fc" 
              dot={false} 
              strokeWidth={2} 
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}