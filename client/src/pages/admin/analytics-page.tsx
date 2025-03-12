
import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

// Sample data for the chart
const data = [
  { name: 'Jan', sessions: 400, users: 240 },
  { name: 'Feb', sessions: 300, users: 139 },
  { name: 'Mar', sessions: 200, users: 980 },
  { name: 'Apr', sessions: 278, users: 390 },
  { name: 'May', sessions: 189, users: 480 },
  { name: 'Jun', sessions: 239, users: 380 },
  { name: 'Jul', sessions: 349, users: 430 },
];

export default function AnalyticsPage() {
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-3xl font-bold mb-6">Analytics Dashboard</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <Card>
          <CardHeader>
            <CardTitle>Total Sessions</CardTitle>
            <CardDescription>Last 30 days</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">1,245</p>
            <p className="text-sm text-muted-foreground">+12.3% from last month</p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle>Active Users</CardTitle>
            <CardDescription>Last 30 days</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">356</p>
            <p className="text-sm text-muted-foreground">+5.4% from last month</p>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle>Station Uptime</CardTitle>
            <CardDescription>Average</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">98.7%</p>
            <p className="text-sm text-muted-foreground">+1.2% from last month</p>
          </CardContent>
        </Card>
      </div>
      
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Usage Overview</CardTitle>
          <CardDescription>Sessions and users over time</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={data}
                margin={{
                  top: 5,
                  right: 30,
                  left: 20,
                  bottom: 5,
                }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="sessions" stroke="hsl(var(--chart-1))" activeDot={{ r: 8 }} />
                <Line type="monotone" dataKey="users" stroke="hsl(var(--chart-2))" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
