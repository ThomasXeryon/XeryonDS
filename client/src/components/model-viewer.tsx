import { Card } from './ui/card';
import { Loader2 } from 'lucide-react';
import { useState, useEffect } from 'react';

export function ModelViewer() {
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoading(false), 500);
    return () => clearTimeout(timer);
  }, []);

  return (
    <Card className="w-full aspect-square bg-gradient-to-b from-background to-accent/10 relative overflow-hidden">
      {isLoading ? (
        <div className="flex items-center justify-center h-full">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : (
        <div className="w-full h-full flex items-center justify-center">
          <div 
            className="w-48 h-12 relative animate-spin-slow" 
            style={{
              transformStyle: 'preserve-3d',
              animation: 'rotate 10s infinite linear',
            }}
          >
            {/* Front face */}
            <div 
              className="absolute inset-0 bg-[#0079C1]"
              style={{
                transform: 'translateZ(20px)',
                boxShadow: '0 0 10px rgba(0,0,0,0.2)',
              }}
            />
            {/* Back face */}
            <div 
              className="absolute inset-0 bg-[#0079C1]/80"
              style={{
                transform: 'translateZ(-20px)',
                boxShadow: '0 0 10px rgba(0,0,0,0.2)',
              }}
            />
            {/* Right face */}
            <div 
              className="absolute inset-0 bg-[#0079C1]/90"
              style={{
                transform: 'rotateY(90deg) translateZ(20px)',
                width: '40px',
                left: 'calc(50% - 20px)',
                boxShadow: '0 0 10px rgba(0,0,0,0.2)',
              }}
            />
            {/* Left face */}
            <div 
              className="absolute inset-0 bg-[#0079C1]/90"
              style={{
                transform: 'rotateY(-90deg) translateZ(20px)',
                width: '40px',
                left: 'calc(50% - 20px)',
                boxShadow: '0 0 10px rgba(0,0,0,0.2)',
              }}
            />
          </div>
        </div>
      )}
    </Card>
  );
}