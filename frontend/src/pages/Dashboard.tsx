import { PageContent, PageHeader } from '../components/PageLayout';
import React, { Suspense, Component, ErrorInfo, ReactNode, memo } from 'react';

// Optimized Material-UI imports for better tree-shaking
import Typography from '@mui/material/Typography';
import Grid from '@mui/material/Grid';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Alert from '@mui/material/Alert';
import LoadingSpinner from '../components/LoadingSpinner';
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

const ExperimentSkeleton: React.FC = () => (
  <Card>
    <CardContent>
      <LoadingSpinner message="Loading experiment data..." minHeight={160} />
    </CardContent>
  </Card>
);

const Dashboard: React.FC = memo(() => {
  return (
    <PageContent>
      <PageHeader title="Dashboard" />

      <Grid container spacing={{ xs: 2, md: 3 }}>
        <Grid item xs={12}>
          <SimpleErrorBoundary>
            <Suspense fallback={<ExperimentSkeleton />}>
              <ExperimentStatus compact={true} />
            </Suspense>
          </SimpleErrorBoundary>
        </Grid>
      </Grid>
    </PageContent>
  );
});

// Add display name for debugging
Dashboard.displayName = 'Dashboard';

export default Dashboard;
