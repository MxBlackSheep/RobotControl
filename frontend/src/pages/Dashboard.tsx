import { PageContent, PageGrid, PageHeader } from '../components/PageLayout';
import React, { Component, ErrorInfo, ReactNode, memo } from 'react';
import { Alert, Box, Typography } from '@mui/material';
import ExperimentStatus from '../components/ExperimentStatus';
import NowRunning from '../components/overview/NowRunning';
import { InstrumentHealth, NeedsAttention, RecentRuns, UpNext } from '../components/overview/OverviewPanels';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { useAuth } from '../context/AuthContext';
import { fontMono } from '../theme';
import { clockTime } from '../utils/displayTime';

/** Keeps a render error in one panel from taking the page down; it keeps the panel's grid span. */
class PanelErrorBoundary extends Component<{ name: string; span?: number; children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.warn(`${this.props.name} panel error (non-critical):`, error, errorInfo);
  }

  render() {
    const span = this.props.span;
    return this.state.hasError
      ? <Box sx={{ gridColumn: { xs: '1 / -1', md: span ? `span ${span}` : '1 / -1' } }}><Alert severity="warning">{this.props.name} is temporarily unavailable</Alert></Box>
      : this.props.children;
  }
}

/** Overview on the 12-column grid of the approved mock: status strip, run and hold, then the two lists. */
const Dashboard: React.FC = memo(() => {
  const { status, error } = useRobotStatusContext();
  const { user } = useAuth();
  const attention = !!robotAttention(status);
  const canOpenScheduling = ['admin', 'user'].includes(user?.role || '');
  return <PageContent>
    <PageHeader title="Overview" actions={status && <Typography sx={{ fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>Updated {clockTime(new Date(status.receivedAt))}</Typography>} />
    <PageGrid>
      <PanelErrorBoundary name="Instrument health"><InstrumentHealth status={status} /></PanelErrorBoundary>
      <PanelErrorBoundary name="Now running" span={attention ? 8 : 12}><NowRunning status={status} error={error} span={attention ? 8 : 12} /></PanelErrorBoundary>
      {attention && <PanelErrorBoundary name="Needs attention" span={4}><NeedsAttention status={status} span={4} /></PanelErrorBoundary>}
      <PanelErrorBoundary name="Up next" span={6}><UpNext canOpenScheduling={canOpenScheduling} span={6} /></PanelErrorBoundary>
      <PanelErrorBoundary name="Recent runs" span={6}><RecentRuns canOpenScheduling={canOpenScheduling} span={6} /></PanelErrorBoundary>
      <PanelErrorBoundary name="Latest experiment"><ExperimentStatus /></PanelErrorBoundary>
    </PageGrid>
  </PageContent>;
});

Dashboard.displayName = 'Dashboard';

export default Dashboard;
