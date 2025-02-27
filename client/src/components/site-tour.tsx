import { useEffect } from 'react';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { useLocation } from 'wouter';
import { useAuth } from '@/hooks/use-auth';

interface SiteTourProps {
  isAdmin?: boolean;
}

export function SiteTour({ isAdmin }: SiteTourProps) {
  const [location] = useLocation();
  const { user } = useAuth();

  useEffect(() => {
    // Only show tour on home page and when user is authenticated
    if (location !== '/' || !user) return;

    // Check if this is the user's first visit
    const hasSeenTour = localStorage.getItem(`hasSeenTour_${user.id}`);
    if (hasSeenTour) return;

    // Add a delay to ensure all elements are rendered after login
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

      // Mark the tour as seen for this specific user
      localStorage.setItem(`hasSeenTour_${user.id}`, 'true');
    }, 2000); // Increased delay to 2 seconds to ensure everything is loaded

    return () => clearTimeout(tourTimeout);
  }, [location, isAdmin, user]);

  return null;
}