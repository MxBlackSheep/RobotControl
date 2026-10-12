import { PageContent, PageGrid, PageHeader } from '../components/PageLayout';
import React, { Component, ErrorInfo, ReactNode, memo } from 'react';
import { Alert, Box, Typography, useMediaQuery, type Theme } from '@mui/material';
import ExperimentStatus from '../components/ExperimentStatus';
import NowRunning from '../components/overview/NowRunning';
import OverviewDeck, { type DeckCard } from '../components/overview/OverviewDeck';
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

/**
 * Overview on the 12-column grid of the approved mock: status strip, run and hold, then the two
 * lists. Below 600px the same panels become a swipeable card deck, the hold first. Only one of the
 * two layouts is mounted, so each panel polls once.
 */
const Dashboard: React.FC = memo(() => {
  const { status, error } = useRobotStatusContext();
  const { user } = useAuth();
  const phone = useMediaQuery((theme: Theme) => theme.breakpoints.down('sm'), { noSsr: true });
  const attention = !!robotAttention(status);
  const canOpenScheduling = ['admin', 'user'].includes(user?.role || '');
  const health = <PanelErrorBoundary key="Instrument health" name="Instrument health"><InstrumentHealth status={status} /></PanelErrorBoundary>;
  const running = <PanelErrorBoundary key="Now running" name="Now running" span={attention ? 8 : 12}><NowRunning status={status} error={error} span={attention ? 8 : 12} /></PanelErrorBoundary>;
  const hold = attention && <PanelErrorBoundary key="Needs attention" name="Needs attention" span={4}><NeedsAttention status={status} span={4} /></PanelErrorBoundary>;
  const upNext = <PanelErrorBoundary key="Up next" name="Up next" span={6}><UpNext canOpenScheduling={canOpenScheduling} span={6} /></PanelErrorBoundary>;
  const recent = <PanelErrorBoundary key="Recent runs" name="Recent runs" span={6}><RecentRuns canOpenScheduling={canOpenScheduling} span={6} /></PanelErrorBoundary>;
  const latest = <PanelErrorBoundary key="Latest experiment" name="Latest experiment"><ExperimentStatus /></PanelErrorBoundary>;
  const cards: DeckCard[] = [
    ...(hold ? [{ name: 'Needs attention', node: hold }] : []),
    { name: 'Now running', node: running },
    { name: 'Instrument health', node: health },
    { name: 'Up next', node: upNext },
    { name: 'Recent runs', node: recent },
    { name: 'Latest experiment', node: latest },
  ];
  return <PageContent>
    <PageHeader title="Overview" actions={status && <Typography sx={{ fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>Updated {clockTime(new Date(status.receivedAt))}</Typography>} />
    {phone
      ? <OverviewDeck cards={cards} />
      : <PageGrid>{health}{running}{hold}{upNext}{recent}{latest}</PageGrid>}
  </PageContent>;
});

Dashboard.displayName = 'Dashboard';

export default Dashboard;
