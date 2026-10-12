import { PageContent, PageGrid, PageHeader } from '../components/PageLayout';
import React, { Component, ErrorInfo, ReactNode, memo, useEffect, useState } from 'react';
import { Alert, Box, Stack, Typography, useMediaQuery, type Theme } from '@mui/material';
import ExperimentStatus from '../components/ExperimentStatus';
import NowRunning from '../components/overview/NowRunning';
import { CleanTips, InstrumentHealth, InstrumentProblems, NeedsAttention, RecentRuns, UpNext } from '../components/overview/OverviewPanels';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { useAuth } from '../context/AuthContext';
import { fontMono, layout } from '../theme';
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

/** Phones show the next three runs; the full list is on the Runs tab. */
const PHONE_UP_NEXT = 3;

/** "Updated 8 s ago": on a phone through the tunnel, how fresh the numbers are matters more than the clock time. */
function UpdatedAgo({ at }: { at: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  return <>Updated {seconds < 60 ? `${seconds} s` : `${Math.round(seconds / 60)} min`} ago</>;
}

/**
 * Overview on the 12-column grid of the approved mock: status strip, run and hold, then the two
 * lists. Below 600px it is the phone's Now tab: one column in order of urgency (the hold, what is
 * running, what is next, clean tips) with instrument health only when something needs a look.
 * Only one of the two layouts is mounted, so each panel polls once.
 */
const Dashboard: React.FC = memo(() => {
  const { status, error } = useRobotStatusContext();
  const { user } = useAuth();
  const phone = useMediaQuery((theme: Theme) => theme.breakpoints.down('sm'), { noSsr: true });
  const attention = !!robotAttention(status);
  const canOpenScheduling = ['admin', 'user'].includes(user?.role || '');
  const running = <PanelErrorBoundary key="Now running" name="Now running" span={attention ? 8 : 12}><NowRunning status={status} error={error} span={attention ? 8 : 12} /></PanelErrorBoundary>;
  const hold = attention && <PanelErrorBoundary key="Needs attention" name="Needs attention" span={4}><NeedsAttention status={status} span={4} /></PanelErrorBoundary>;
  const updated = status && <Typography sx={{ fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>
    {phone ? <UpdatedAgo at={status.receivedAt} /> : `Updated ${clockTime(new Date(status.receivedAt))}`}
  </Typography>;
  if (phone) return <PageContent>
    <PageHeader title="Now" actions={updated} />
    <Stack spacing={`${layout.gutter}px`}>
      {hold}
      {running}
      <PanelErrorBoundary name="Up next"><UpNext canOpenScheduling={canOpenScheduling} rows={PHONE_UP_NEXT} /></PanelErrorBoundary>
      {canOpenScheduling && <PanelErrorBoundary name="Clean tips"><CleanTips /></PanelErrorBoundary>}
      <PanelErrorBoundary name="Instrument health"><InstrumentProblems status={status} /></PanelErrorBoundary>
    </Stack>
  </PageContent>;
  return <PageContent>
    <PageHeader title="Overview" actions={updated} />
    <PageGrid>
      <PanelErrorBoundary name="Instrument health"><InstrumentHealth status={status} /></PanelErrorBoundary>
      {running}{hold}
      <PanelErrorBoundary name="Up next" span={6}><UpNext canOpenScheduling={canOpenScheduling} span={6} /></PanelErrorBoundary>
      <PanelErrorBoundary name="Recent runs" span={6}><RecentRuns canOpenScheduling={canOpenScheduling} span={6} /></PanelErrorBoundary>
      <PanelErrorBoundary name="Latest experiment"><ExperimentStatus /></PanelErrorBoundary>
    </PageGrid>
  </PageContent>;
});

Dashboard.displayName = 'Dashboard';

export default Dashboard;
