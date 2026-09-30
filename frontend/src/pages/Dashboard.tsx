import { PageContent, PageHeader } from '../components/PageLayout';
import React, { Component, ErrorInfo, ReactNode, memo } from 'react';
import { Alert, Box, Card } from '@mui/material';
import ExperimentStatus from '../components/ExperimentStatus';
import NowRunning from '../components/overview/NowRunning';
import { InstrumentHealth, NeedsAttention, RecentRuns, UpNext } from '../components/overview/OverviewPanels';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { useAuth } from '../context/AuthContext';

/** Keeps a render error in one panel from taking the page down. */
class PanelErrorBoundary extends Component<{ name: string; children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.warn(`${this.props.name} panel error (non-critical):`, error, errorInfo);
  }

  render() {
    return this.state.hasError
      ? <Card variant="outlined" sx={{ p: 2 }}><Alert severity="warning">{this.props.name} is temporarily unavailable</Alert></Card>
      : this.props.children;
  }
}

const Dashboard: React.FC = memo(() => {
  const { status, error } = useRobotStatusContext();
  const { user } = useAuth();
  const attention = !!robotAttention(status);
  const canOpenScheduling = ['admin', 'user'].includes(user?.role || '');
  return <PageContent>
    <PageHeader title="Overview" />
    <Box sx={{ display: 'grid', gap: 2 }}>
      {/* On phones the hold comes first: it blocks every other run. */}
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', md: attention ? 'minmax(0,1.6fr) minmax(0,1fr)' : '1fr' } }}>
        <Box sx={{ order: { xs: 2, md: 1 }, minWidth: 0, display: 'grid' }}><PanelErrorBoundary name="Now running"><NowRunning status={status} error={error} /></PanelErrorBoundary></Box>
        {attention && <Box sx={{ order: { xs: 1, md: 2 }, minWidth: 0, display: 'grid' }}><PanelErrorBoundary name="Needs attention"><NeedsAttention status={status} /></PanelErrorBoundary></Box>}
      </Box>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'minmax(0,1fr)', '@container workspace (min-width: 1000px)': { gridTemplateColumns: 'minmax(0,1fr) 360px' }, alignItems: 'start' }}>
        <Box sx={{ display: 'grid', gap: 2, minWidth: 0 }}>
          <PanelErrorBoundary name="Up next"><UpNext canOpenScheduling={canOpenScheduling} /></PanelErrorBoundary>
          <PanelErrorBoundary name="Recent runs"><RecentRuns /></PanelErrorBoundary>
        </Box>
        <Box sx={{ display: 'grid', gap: 2, minWidth: 0 }}>
          <PanelErrorBoundary name="Instrument health"><InstrumentHealth status={status} /></PanelErrorBoundary>
          <PanelErrorBoundary name="Latest experiment"><ExperimentStatus /></PanelErrorBoundary>
        </Box>
      </Box>
    </Box>
  </PageContent>;
});

Dashboard.displayName = 'Dashboard';

export default Dashboard;
