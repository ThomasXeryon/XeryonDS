import { useEffect } from 'react';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useLocation } from 'wouter';

interface SiteTourProps {
  isAdmin?: boolean;
}

export function SiteTour({ isAdmin }: SiteTourProps) {
  const [location] = useLocation();

  useEffect(() => {
    // Only show tour on home page
    if (location !== '/') return;

    // Check if this is the user's first visit
    const hasSeenTour = localStorage.getItem('hasSeenTour');
    if (hasSeenTour) return;

    // Add a slight delay to ensure all elements are rendered
    const tourTimeout = setTimeout(() => {
      const driverObj = driver({
        showProgress: true,
        animate: true,
        steps: [
          {
            element: '#demo-stations',
            popover: {
              title: 'Welcome to Xeryon Demo Platform',
              description: 'This is where you can view and control available demo stations.',
              side: "bottom" as const,
              align: 'start' as const
            }
          },
          {
            element: '.station-card',
            popover: {
              title: 'Demo Stations',
              description: 'Click on any station to start a demo session. Each session lasts 5 minutes.',
              side: "right" as const,
              align: 'start' as const
            }
          },
          {
            element: '#user-controls',
            popover: {
              title: 'User Controls',
              description: 'Access your account settings and logout from here.',
              side: "bottom" as const,
              align: 'end' as const
            }
          },
          ...(isAdmin ? [
            {
              element: '#admin-dashboard',
              popover: {
                title: 'Admin Dashboard',
                description: 'Manage stations, users, and view analytics here.',
                side: "bottom" as const,
                align: 'start' as const
              }
            }
          ] : []),
          {
            element: '#feedback-button',
            popover: {
              title: 'Feedback & Support',
              description: 'Click here to report issues or provide feedback about the platform.',
              side: "left" as const,
              align: 'start' as const
            }
          }
        ]
      });

      // Start the tour
      driverObj.drive();

      // Mark the tour as seen
      localStorage.setItem('hasSeenTour', 'true');
    }, 1000); // 1 second delay

    return () => clearTimeout(tourTimeout);
  }, [location, isAdmin]);

  return null;
}