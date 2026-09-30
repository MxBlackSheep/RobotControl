import { PageContent, PageHeader } from '../components/PageLayout';
import React, { Component, ErrorInfo, ReactNode, memo } from 'react';
import { Alert, Card } from '@mui/material';
import ExperimentStatus from '../components/ExperimentStatus';

/** Keeps a render error in the card from taking the page down. */
class WidgetErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.warn('ExperimentStatus widget error (non-critical):', error, errorInfo);
  }

  render() {
    return this.state.hasError
      ? <Card sx={{ p: 2 }}><Alert severity="warning">Experiment widget temporarily unavailable</Alert></Card>
      : this.props.children;
  }
}

const Dashboard: React.FC = memo(() => (
  <PageContent>
    <PageHeader title="Overview" />
    <WidgetErrorBoundary>
      <ExperimentStatus />
    </WidgetErrorBoundary>
  </PageContent>
));

Dashboard.displayName = 'Dashboard';

export default Dashboard;
