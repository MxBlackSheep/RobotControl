import React from 'react';
import { Alert, Box, Button, LinearProgress, Typography, useMediaQuery, type Theme } from '@mui/material';
import StatusChip from '../components/StatusChip';
import { fontMono, layout } from '../theme';
import { dayTime } from '../utils/displayTime';
import Refresh from '@mui/icons-material/Refresh';
import { ListRow, PageContent, PageGrid, PageHeader, Panel } from '../components/PageLayout';
import type { StatusTone } from '../theme';
import useMonitoring, { type DatabaseConnection } from '../hooks/useMonitoring';

export default function MonitoringPage() {
  // This page owns one monitoring request cycle. Presentation below never starts polling.
  const { monitoringData, systemHealth, databases, streamingStatus, isLoading, error, refreshData } = useMonitoring();
  // From md each metric card has room for its detail in the header band; narrower, it goes under the value.
  const wide = useMediaQuery((theme: Theme) => theme.breakpoints.up('md'), { noSsr: true });
  const timestamp = systemHealth?.timestamp || monitoringData?.last_updated;
  const sessionCount = streamingStatus?.active_session_count;
  const sessionLimit = streamingStatus?.max_sessions;
  const sessionSummary = Number.isInteger(sessionCount) && sessionCount! >= 0
    ? Number.isInteger(sessionLimit) && sessionLimit! > 0
      ? `${sessionCount} of ${sessionLimit} slots in use`
      : `${sessionCount} slots in use`
    : 'Unavailable';
  const capacity = (used?: number, total?: number) => Number.isFinite(used) && Number.isFinite(total)
    ? `${used} / ${total} GB` : '';
  // An unknown share (first sample, unreadable process tree) shows a dash, never 0 %.
  const percent = (value?: number | null) => Number.isFinite(value) ? `${Math.round(value!)}%` : '—';
  const metrics = [
    { name: 'CPU', value: systemHealth?.cpu_percent, detail: systemHealth ? `RobotControl ${percent(systemHealth.robotcontrol_cpu_percent)}` : '' },
    { name: 'Memory', value: systemHealth?.memory_percent, detail: capacity(systemHealth?.memory_used_gb, systemHealth?.memory_total_gb) },
    { name: 'Disk', value: systemHealth?.disk_percent, detail: capacity(systemHealth?.disk_used_gb, systemHealth?.disk_total_gb) },
  ];
  // After a failed read the last state stays, in neutral colour beside "Stale data".
  // A connection that is not reported as connected never counts as healthy.
  const connectionState = (connection: DatabaseConnection): [string, StatusTone] => connection.state === 'connected' ? ['Connected', error ? 'neutral' : 'completed']
    : connection.state === 'failed' ? ['Cannot connect', error ? 'neutral' : 'fault'] : ['Unknown', 'neutral'];
  const connections = databases ? [databases.built_in, ...(databases.connections ?? [])].filter((x): x is DatabaseConnection => Boolean(x)) : [];
  const failing = connections.filter(connection => connection.state === 'failed').length;
  const allKnown = Boolean(databases?.built_in && databases.connections) && connections.every(connection => ['connected', 'failed'].includes(connection.state));
  const database: [string, StatusTone] = !databases ? ['Unavailable', 'neutral']
    : failing ? [`${failing} cannot connect`, error ? 'neutral' : 'fault']
    : allKnown ? ['Connected', error ? 'neutral' : 'completed'] : ['Partly unknown', 'neutral'];
  const liveView: [string, StatusTone] = streamingStatus?.enabled === true ? ['Enabled', 'completed'] : streamingStatus?.enabled === false ? ['Disabled', 'neutral'] : ['Unavailable', 'neutral'];
  return <PageContent variant="overview">
    <PageHeader title="System status" actions={<>
      <StatusChip tone={error ? 'attention' : 'neutral'} label={error ? monitoringData ? 'Stale data' : 'Unavailable' : isLoading ? 'Updating' : monitoringData ? 'Updated' : 'Unknown'} />
      {timestamp && <Typography variant="caption" color="text.secondary">Last reading {dayTime(timestamp)}</Typography>}
      <Button variant="outlined" startIcon={<Refresh />} disabled={isLoading} onClick={() => void refreshData()}>Refresh</Button>
    </>} />
    {error && <Alert severity="warning" sx={{ mb: `${layout.gutter}px` }}>{error}{monitoringData ? ' · Last reading retained.' : ''}</Alert>}
    {isLoading && <LinearProgress aria-label="Updating monitoring" sx={{ mb: `${layout.gutter}px` }} />}
    <PageGrid>
      {/* Below md the three cards share one row (detail under the value), so the Databases state
          stays on a phone's first screen; from md the wrapper disappears into the 12-column grid. */}
      <Box sx={{ display: { xs: 'grid', md: 'contents' }, gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: `${layout.gutter}px`, minWidth: 0 }}>
      {metrics.map(metric => {
        return <Panel key={metric.name} title={metric.name} span={4}
          actions={wide && metric.detail && <Typography variant="caption" color="text.secondary" sx={{ fontFamily: fontMono }}>{metric.detail}</Typography>}
          sx={{ gridColumn: { xs: 'auto', md: 'span 4' } }} bodySx={{ px: { xs: 1.5, md: `${layout.inset}px` } }}>
          <Typography sx={{ fontFamily: fontMono, fontSize: { xs: 24, md: 32 }, lineHeight: { xs: '32px', md: '40px' }, fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}>{percent(metric.value)}</Typography>
          <LinearProgress aria-label={`${metric.name} usage`} variant="determinate" value={Number.isFinite(metric.value) ? Math.max(0, Math.min(100, metric.value!)) : 0}
            color={metric.value! > 90 ? 'error' : metric.value! > 80 ? 'warning' : 'primary'} sx={{ mt: 1, height: 8, borderRadius: 1, bgcolor: 'surface.track', visibility: Number.isFinite(metric.value) ? 'visible' : 'hidden' }} />
          {/* The narrow card's copy uses the text font, so "RobotControl 9%" wraps at the space. */}
          {!wide && metric.detail && <Typography variant="caption" component="p" color="text.secondary" sx={{ mt: 1 }}>{metric.detail}</Typography>}
        </Panel>;
      })}
      </Box>
      <Panel title="Databases" span={8} inset={false} actions={<StatusChip tone={database[1]} label={database[0]} />}>
        {!databases ? <Typography variant="body2" color="text.secondary" sx={{ p: `${layout.inset}px` }}>Connection checks are unavailable.</Typography>
          : <Box component="ul" sx={{ m: 0, p: 0, listStyle: 'none' }}>
            {connections.map(connection => <DatabaseRow key={connection.id} connection={connection} state={connectionState(connection)} />)}
            {databases.connections === null && <DatabaseRow connection={{ id: 'saved', name: 'Saved connections', access: '', uses: [], state: 'unknown',
              message: 'The saved connections could not be checked.' }} state={['Unknown', 'neutral']} />}
            {databases.connections?.length === 0 && <ListRow component="li" columns="minmax(0, 1fr)" sx={{ height: 'auto', minHeight: layout.row, py: 1, '& > *': { whiteSpace: 'normal' } }}>
              <Typography variant="body2" color="text.secondary">No saved connections. Add them in Database → Database settings.</Typography></ListRow>}
          </Box>}
      </Panel>
      <ServiceCard span={4} title="Live view" state={liveView} rows={[['Sessions', sessionSummary]]} />
    </PageGrid>
  </PageContent>;
}

function ServiceCard({ title, span, state: [label, tone], rows, children }: { title: string; span: number; state: [string, StatusTone]; rows: [string, string][]; children?: React.ReactNode }) {
  return <Panel title={title} span={span} inset={false} actions={<StatusChip tone={tone} label={label} />}>
    <Box component="dl" sx={{ m: 0 }}>
      {/* Identifiers can be long (server names); these rows grow rather than clip. */}
      {rows.map(([name, value]) => <ListRow key={name} columns={{ xs: '112px minmax(0, 1fr)', sm: '160px minmax(0, 1fr)' }} sx={{ height: 'auto', minHeight: layout.row, py: 1, '& > *': { whiteSpace: 'normal', overflowWrap: 'anywhere' } }}>
        <Typography component="dt" variant="body2" color="text.secondary">{name}</Typography><Typography component="dd" variant="body2" sx={{ m: 0 }}>{value}</Typography>
      </ListRow>)}
    </Box>
    {children}
  </Panel>;
}

const accessLabel: Record<string, string> = { 'built-in': 'Built-in', read: 'Read-only', operation: 'Database changes' };

function DatabaseRow({ connection, state: [label, tone] }: { connection: DatabaseConnection; state: [string, StatusTone] }) {
  const target = [connection.server, connection.database].filter(Boolean).join(' / ');
  const details = [accessLabel[connection.access] ?? '', connection.uses.length ? connection.uses.join(' · ') : connection.access ? 'Not used' : ''].filter(Boolean).join(' · ');
  // Names and server identifiers can be long; the row grows rather than clipping them.
  return <ListRow component="li" columns="minmax(0, 1fr) auto" sx={{ height: 'auto', minHeight: layout.row, py: 1, alignItems: 'start',
    '& > *:first-of-type': { whiteSpace: 'normal', overflowWrap: 'anywhere' } }}>
    <Box>
      <Typography variant="body2" sx={{ fontWeight: 600 }}>{connection.name}</Typography>
      {target && <Typography variant="caption" component="div" color="text.secondary" sx={{ fontFamily: fontMono }}>{target}</Typography>}
      {details && <Typography variant="caption" component="div" color="text.secondary">{details}</Typography>}
      {connection.state !== 'connected' && connection.message && <Typography variant="caption" component="div" color={connection.state === 'failed' ? 'error' : 'text.secondary'}>{connection.message}</Typography>}
    </Box>
    <StatusChip tone={tone} label={label} />
  </ListRow>;
}
