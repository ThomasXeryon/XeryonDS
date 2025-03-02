import { Canvas } from '@react-three/fiber';
import { OrbitControls, Stage, useGLTF } from '@react-three/drei';
import { Suspense, useState } from 'react';
import { Card } from './ui/card';
import { Loader2 } from 'lucide-react';
import { Button } from './ui/button';
import { useMutation } from '@tanstack/react-query';
import { apiRequest } from '@/lib/queryClient';
import { useToast } from '@/hooks/use-toast';

function Model({ url }: { url?: string }) {
  // If no URL provided, show a placeholder box
  if (!url) {
    return (
      <mesh>
        <boxGeometry args={[1, 0.2, 0.5]} /> {/* Represent actuator dimensions */}
        <meshStandardMaterial color="#0079C1" /> {/* Xeryon blue */}
      </mesh>
    );
  }

  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

export function ModelViewer({ modelUrl }: { modelUrl?: string }) {
  const [uploadedUrl, setUploadedUrl] = useState<string | undefined>(modelUrl);
  const { toast } = useToast();

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      // Read file as base64
      const reader = new FileReader();
      const base64Promise = new Promise<string>((resolve, reject) => {
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = reject;
      });
      reader.readAsDataURL(file);

      const base64Data = await base64Promise;

      const res = await apiRequest("POST", "/api/models/upload", {
        file: base64Data,
        filename: file.name
      });

      return (await res.json()).url;
    },
    onSuccess: (url) => {
      setUploadedUrl(url);
      toast({
        title: "Model uploaded successfully",
        description: "Your 3D model is now ready for viewing",
      });
    },
    onError: (error: Error) => {
      toast({
        title: "Upload failed",
        description: error.message,
        variant: "destructive",
      });
    },
  });

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      if (!file.name.toLowerCase().endsWith('.gltf') && !file.name.toLowerCase().endsWith('.glb')) {
        toast({
          title: "Invalid file format",
          description: "Please upload a GLTF or GLB file",
          variant: "destructive",
        });
        return;
      }
      uploadMutation.mutate(file);
    }
  };

  return (
    <Card className="w-full aspect-square bg-gradient-to-b from-background to-accent/10 relative overflow-hidden">
      <div className="absolute top-4 right-4 z-10">
        <input
          type="file"
          accept=".gltf,.glb"
          onChange={handleFileUpload}
          className="hidden"
          id="model-upload"
        />
        <label htmlFor="model-upload">
          <Button
            variant="outline"
            className="bg-background/80 backdrop-blur-sm"
            disabled={uploadMutation.isPending}
          >
            {uploadMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              'Upload GLTF/GLB File'
            )}
          </Button>
        </label>
      </div>

      <Suspense fallback={
        <div className="flex items-center justify-center h-full">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      }>
        <Canvas 
          shadows 
          dpr={[1, 2]} 
          camera={{ fov: 45, position: [0, 0, 3] }}
        >
          <Stage environment="city" intensity={0.6}>
            <Model url={uploadedUrl} />
          </Stage>
          <OrbitControls
            autoRotate
            autoRotateSpeed={4}
            enableZoom={true}
            maxDistance={10}
            minDistance={2}
          />
        </Canvas>
      </Suspense>
    </Card>
  );
}