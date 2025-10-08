import React, { Suspense, Component, ErrorInfo, ReactNode, memo, useCallback } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Box from '@mui/material/Box';
import Container from '@mui/material/Container';
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Button from '@mui/material/Button';
import Alert from '@mui/material/Alert';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { CardLoading } from '../components/LoadingSpinner';
import ExperimentStatus from '../components/ExperimentStatus';
// Simple Error Boundary Component
interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class SimpleErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.warn('ExperimentStatus widget error (non-critical):', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <Card>
          <CardContent>
            <Alert severity="warning">
              <Typography variant="body2">
                Experiment widget temporarily unavailable
              </Typography>
            </Alert>
          </CardContent>
        </Card>
      );
    }

    return this.props.children;
  }
}

// Loading component for experiment widget - using shared LoadingSpinner
const ExperimentSkeleton: React.FC = memo(() => (
  <CardLoading 
    lines={4} 
    message="Loading experiment data..." 
  />
));

// Add display name for debugging
ExperimentSkeleton.displayName = 'ExperimentSkeleton';

const Dashboard: React.FC = memo(() => {
  const navigate = useNavigate();
  const { user } = useAuth();

  // Memoized navigation handlers with route validation for better performance
  const handleNavigateToDatabase = useCallback(() => {
    navigate('/database');
  }, [navigate]);
  
  const handleNavigateToCamera = useCallback(() => {
    navigate('/camera');
  }, [navigate]);
  
  const handleNavigateToScheduling = useCallback(() => {
    // Validate user role before navigation
    if (['admin', 'user'].includes(user?.role || '')) {
      navigate('/scheduling');
    } else {
      console.warn('Access denied: User does not have permission to access scheduling');
    }
  }, [navigate, user?.role]);
  
  const handleNavigateToSystemStatus = useCallback(() => {
    navigate('/system-status');
  }, [navigate]);

  const handleNavigateToAbout = useCallback(() => {
    navigate('/about');
  }, [navigate]);

  return (
    <Container 
      maxWidth="lg" 
      sx={{ 
        mt: { xs: 2, md: 4 }, 
        mb: { xs: 2, md: 4 },
        px: { xs: 2, sm: 3 }
      }}
    >
      <Typography 
        variant="h4" 
        gutterBottom
        sx={{ mb: { xs: 2, md: 3 } }}
      >
        System Dashboard
      </Typography>

      <Grid container spacing={{ xs: 2, md: 3 }}>

        {/* Latest Experiment Status */}
        <Grid item xs={12} lg={6}>
          <SimpleErrorBoundary>
            <Suspense fallback={<ExperimentSkeleton />}>
              <ExperimentStatus compact={true} />
            </Suspense>
          </SimpleErrorBoundary>
        </Grid>

        {/* Quick Actions */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
              <Typography variant="h6" gutterBottom>
                Quick Actions
              </Typography>
              <Box sx={{ 
                display: 'flex', 
                flexDirection: 'column', 
                gap: { xs: 1.5, sm: 2 } 
              }}>
                <Button
                  variant="contained"
                  onClick={handleNavigateToDatabase}
                  fullWidth
                  sx={{ 
                    minHeight: { xs: 44, sm: 36 },
                    fontSize: { xs: '0.875rem', sm: '0.875rem' }
                  }}
                >
                  Browse Database Tables
                </Button>
                <Button
                  variant="contained"
                  onClick={handleNavigateToCamera}
                  fullWidth
                  color="secondary"
                  sx={{ 
                    minHeight: { xs: 44, sm: 36 },
                    fontSize: { xs: '0.875rem', sm: '0.875rem' }
                  }}
                >
                  Camera System
                </Button>
                {(['admin', 'user'].includes(user?.role || '')) && (
                  <Button
                    variant="contained"
                    onClick={handleNavigateToScheduling}
                    fullWidth
                    color="info"
                    sx={{ 
                      minHeight: { xs: 44, sm: 36 },
                      fontSize: { xs: '0.875rem', sm: '0.875rem' }
                    }}
                  >
                    Experiment Scheduling
                  </Button>
                )}
                <Button
                  variant="contained"
                  onClick={handleNavigateToSystemStatus}
                  fullWidth
                  color="success"
                  sx={{ 
                    minHeight: { xs: 44, sm: 36 },
                    fontSize: { xs: '0.875rem', sm: '0.875rem' }
                  }}
                >
                  System Status
                </Button>
                <Button
                  variant="outlined"
                  onClick={handleNavigateToAbout}
                  fullWidth
                  sx={{ 
                    minHeight: { xs: 44, sm: 36 },
                    fontSize: { xs: '0.875rem', sm: '0.875rem' }
                  }}
                >
                  About PyRobot
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Container>
  );
});

// Add display name for debugging
Dashboard.displayName = 'Dashboard';

export default Dashboard;
