import { useEffect } from 'react';
import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';

interface SiteTourProps {
  isAdmin?: boolean;
}

export function SiteTour({ isAdmin }: SiteTourProps) {
  useEffect(() => {
    // Check if this is the user's first visit
    const hasSeenTour = localStorage.getItem('hasSeenTour');
    if (hasSeenTour) return;

    const driverObj = driver({
      showProgress: true,
      animate: true,
      steps: [
        {
          element: '#demo-stations',
          popover: {
            title: 'Welcome to Xeryon Demo Platform',
            description: 'This is where you can view and control available demo stations.',
            side: "bottom",
            align: 'start'
          }
        },
        {
          element: '.station-card',
          popover: {
            title: 'Demo Stations',
            description: 'Click on any station to start a demo session. Each session lasts 5 minutes.',
            side: "right",
            align: 'start'
          }
        },
        {
          element: '#user-controls',
          popover: {
            title: 'User Controls',
            description: 'Access your account settings and logout from here.',
            side: "bottom",
            align: 'end'
          }
        },
        ...(isAdmin ? [
          {
            element: '#admin-dashboard',
            popover: {
              title: 'Admin Dashboard',
              description: 'Manage stations, users, and view analytics here.',
              side: "bottom",
              align: 'start'
            }
          }
        ] : []),
        {
          element: '#feedback-button',
          popover: {
            title: 'Feedback & Support',
            description: 'Click here to report issues or provide feedback about the platform.',
            side: "left",
            align: 'start'
          }
        }
      ]
    });

    // Start the tour
    driverObj.drive();

    // Mark the tour as seen
    localStorage.setItem('hasSeenTour', 'true');
  }, [isAdmin]);

  return null;
}
