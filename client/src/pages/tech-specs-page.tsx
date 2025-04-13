import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { 
  Activity, Wrench, Ruler, Settings, FileText, Cpu, 
  Plus, Pencil, RefreshCw, AlertTriangle, InfoIcon 
} from "lucide-react";

interface TechnicalSpec {
  id: number;
  stationId: number;
  modelNumber: string;
  actuatorType: string;
  travelRange: number;
  resolution: number;
  maxSpeed: number;
  maxForce: number;
  operatingVoltage: number;
  dimensions: string;
  weight: number;
  communicationInterface: string;
  encoderType: string;
  softwareVersion: string;
  firmwareVersion: string;
  additionalFeatures?: any;
  installationDate?: string;
  lastMaintenanceDate?: string;
  createdAt: string;
  updatedAt: string;
}

export function TechSpecsPage() {
  const [selectedStation, setSelectedStation] = useState<number | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  
  // Check if user is admin
  useEffect(() => {
    fetch('/api/auth/me')
      .then(res => res.json())
      .then(data => {
        if (data && data.isAdmin) {
          setIsAdmin(true);
        }
      })
      .catch(() => setIsAdmin(false));
  }, []);
  
  // Fetch stations to populate dropdown
  const { data: stations, isLoading: stationsLoading } = useQuery({
    queryKey: ['/api/stations'],
    queryFn: async () => {
      const response = await fetch('/api/stations');
      if (!response.ok) {
        throw new Error('Failed to fetch stations');
      }
      return response.json();
    }
  });
  
  // Set the first station as default when data is loaded
  useEffect(() => {
    if (stations && stations.length > 0 && !selectedStation) {
      setSelectedStation(stations[0].id);
    }
  }, [stations, selectedStation]);
  
  // Fetch technical specs for selected station
  const { 
    data: techSpecs, 
    isLoading: techSpecsLoading, 
    error: techSpecsError,
    refetch: refetchTechSpecs
  } = useQuery({
    queryKey: ['/api/technical-specs', selectedStation],
    queryFn: async () => {
      if (!selectedStation) return null;
      
      const response = await fetch(`/api/technical-specs/${selectedStation}`);
      if (response.status === 404) {
        return null; // No specs yet
      }
      if (!response.ok) {
        throw new Error('Failed to fetch technical specifications');
      }
      return response.json() as Promise<TechnicalSpec>;
    },
    enabled: !!selectedStation
  });
  
  // Format date for display
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Not specified';
    return new Date(dateString).toLocaleDateString();
  };
  
  if (stationsLoading) {
    return <div className="flex justify-center items-center min-h-screen">Loading stations...</div>;
  }
  
  if (!stations || stations.length === 0) {
    return (
      <div className="p-4">
        <Card className="max-w-4xl mx-auto">
          <CardHeader>
            <CardTitle>Technical Specifications</CardTitle>
          </CardHeader>
          <CardContent>
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>No Stations Available</AlertTitle>
              <AlertDescription>
                No stations are currently configured in the system. Please add a station first.
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      </div>
    );
  }
  
  return (
    <div className="p-4">
      <Card className="max-w-5xl mx-auto">
        <CardHeader>
          <CardTitle>Technical Specifications</CardTitle>
          <CardDescription>
            View detailed technical specifications for the selected station
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row justify-between gap-4 mb-6">
            <div className="space-y-2 w-full md:w-1/2">
              <Label htmlFor="station-select">Select Station</Label>
              <Select 
                value={selectedStation?.toString() || ''} 
                onValueChange={(value) => setSelectedStation(parseInt(value))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a station" />
                </SelectTrigger>
                <SelectContent>
                  {stations.map((station: any) => (
                    <SelectItem key={station.id} value={station.id.toString()}>
                      {station.name} ({station.rpiId})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            
            <div className="flex items-end">
              <Button variant="default" onClick={() => refetchTechSpecs()} className="w-full md:w-auto">
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
            </div>
          </div>
          
          {techSpecsLoading ? (
            <div className="h-48 flex justify-center items-center">
              <p>Loading technical specifications...</p>
            </div>
          ) : techSpecsError ? (
            <Alert variant="destructive" className="mb-6">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>
                Failed to load technical specifications. Please try refreshing.
              </AlertDescription>
            </Alert>
          ) : !techSpecs ? (
            <div className="text-center p-8 border rounded-lg">
              <Settings className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium mb-2">No Technical Specifications Available</h3>
              <p className="text-muted-foreground mb-4">
                Technical specifications for this station have not been added yet.
              </p>
              
              {isAdmin && (
                <Dialog>
                  <DialogTrigger asChild>
                    <Button variant="default">
                      <Plus className="h-4 w-4 mr-2" />
                      Add Specifications
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="sm:max-w-[425px]">
                    <DialogHeader>
                      <DialogTitle>Add Technical Specifications</DialogTitle>
                      <DialogDescription>
                        Add technical specifications for this station. This will be displayed to users.
                      </DialogDescription>
                    </DialogHeader>
                    <div className="grid gap-4 py-4">
                      <div className="grid gap-2">
                        <Label htmlFor="model">Model Number</Label>
                        <Input id="model" placeholder="e.g. XLA-5000" />
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="actuatorType">Actuator Type</Label>
                        <Input id="actuatorType" placeholder="e.g. Linear" />
                      </div>
                    </div>
                    <DialogFooter>
                      <Button type="submit" disabled>Add Specifications</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              )}
            </div>
          ) : (
            <>
              <div className="mb-6">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-2xl font-bold">
                    {techSpecs.modelNumber}
                  </h2>
                  
                  {isAdmin && (
                    <Button variant="outline" size="sm">
                      <Pencil className="h-4 w-4 mr-2" />
                      Edit
                    </Button>
                  )}
                </div>
                
                <div className="text-muted-foreground mb-4">
                  <p>Last updated: {formatDate(techSpecs.updatedAt)}</p>
                </div>
              </div>
              
              <Tabs defaultValue="general">
                <TabsList className="mb-4">
                  <TabsTrigger value="general">
                    <InfoIcon className="h-4 w-4 mr-2" />
                    General
                  </TabsTrigger>
                  <TabsTrigger value="performance">
                    <Activity className="h-4 w-4 mr-2" />
                    Performance
                  </TabsTrigger>
                  <TabsTrigger value="dimensions">
                    <Ruler className="h-4 w-4 mr-2" />
                    Physical
                  </TabsTrigger>
                  <TabsTrigger value="software">
                    <Cpu className="h-4 w-4 mr-2" />
                    Software
                  </TabsTrigger>
                </TabsList>
                
                <TabsContent value="general">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">General Specifications</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <Table>
                        <TableBody>
                          <TableRow>
                            <TableCell className="font-medium">Model Number</TableCell>
                            <TableCell>{techSpecs.modelNumber}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Actuator Type</TableCell>
                            <TableCell>{techSpecs.actuatorType}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Communication Interface</TableCell>
                            <TableCell>{techSpecs.communicationInterface}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Encoder Type</TableCell>
                            <TableCell>{techSpecs.encoderType}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Installation Date</TableCell>
                            <TableCell>{formatDate(techSpecs.installationDate)}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Last Maintenance</TableCell>
                            <TableCell>{formatDate(techSpecs.lastMaintenanceDate)}</TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                </TabsContent>
                
                <TabsContent value="performance">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">Performance Specifications</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <Table>
                        <TableBody>
                          <TableRow>
                            <TableCell className="font-medium">Travel Range</TableCell>
                            <TableCell>{techSpecs.travelRange} mm</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Resolution</TableCell>
                            <TableCell>{techSpecs.resolution} nm</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Maximum Speed</TableCell>
                            <TableCell>{techSpecs.maxSpeed} mm/s</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Maximum Force</TableCell>
                            <TableCell>{techSpecs.maxForce} N</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Operating Voltage</TableCell>
                            <TableCell>{techSpecs.operatingVoltage} V</TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                </TabsContent>
                
                <TabsContent value="dimensions">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">Physical Specifications</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <Table>
                        <TableBody>
                          <TableRow>
                            <TableCell className="font-medium">Dimensions</TableCell>
                            <TableCell>{techSpecs.dimensions}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Weight</TableCell>
                            <TableCell>{techSpecs.weight} g</TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                    </CardContent>
                  </Card>
                </TabsContent>
                
                <TabsContent value="software">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">Software/Firmware</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <Table>
                        <TableBody>
                          <TableRow>
                            <TableCell className="font-medium">Software Version</TableCell>
                            <TableCell>{techSpecs.softwareVersion}</TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell className="font-medium">Firmware Version</TableCell>
                            <TableCell>{techSpecs.firmwareVersion}</TableCell>
                          </TableRow>
                        </TableBody>
                      </Table>
                      
                      {techSpecs.additionalFeatures && (
                        <div className="mt-6">
                          <h3 className="text-base font-semibold mb-2">Additional Features</h3>
                          <div className="text-sm">
                            {Object.entries(techSpecs.additionalFeatures).map(([key, value]) => (
                              <div key={key} className="flex items-start py-2 border-b last:border-0">
                                <div className="font-medium mr-2">
                                  {key.replace(/([A-Z])/g, ' $1').replace(/^./, str => str.toUpperCase())}:
                                </div>
                                <div>{String(value)}</div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}