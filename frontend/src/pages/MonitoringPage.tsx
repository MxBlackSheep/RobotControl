import React from 'react';
import { Alert, Box, Button, LinearProgress, Typography } from '@mui/material';
import StatusChip from '../components/StatusChip';
import { fontMono, layout } from '../theme';
import { dayTime } from '../utils/displayTime';
import Refresh from '@mui/icons-material/Refresh';
import { ListRow, PageContent, PageGrid, PageHeader, Panel } from '../components/PageLayout';
import type { StatusTone } from '../theme';
import useMonitoring from '../hooks/useMonitoring';

export default function MonitoringPage() {
  // This page owns one monitoring request cycle. Presentation below never starts polling.
  const { monitoringData, systemHealth, databaseStatus, streamingStatus, isLoading, error, refreshData } = useMonitoring();
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
  const metrics = [
    { name: 'CPU', value: systemHealth?.cpu_percent },
    { name: 'Memory', value: systemHealth?.memory_percent, detail: capacity(systemHealth?.memory_used_gb, systemHealth?.memory_total_gb) },
    { name: 'Disk', value: systemHealth?.disk_percent, detail: capacity(systemHealth?.disk_used_gb, systemHealth?.disk_total_gb) },
  ];
  // After a failed read the last state stays, in neutral colour beside "Stale data".
  const database: [string, StatusTone] = databaseStatus?.is_connected === true ? ['Connected', error ? 'neutral' : 'completed']
    : databaseStatus?.is_connected === false ? ['Disconnected', error ? 'neutral' : 'fault'] : ['Unavailable', 'neutral'];
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
      {metrics.map(metric => <Panel key={metric.name} title={metric.name} span={4}
        actions={metric.detail && <Typography variant="caption" color="text.secondary" sx={{ fontFamily: fontMono }}>{metric.detail}</Typography>}>
        <Typography sx={{ fontFamily: fontMono, fontSize: 32, lineHeight: '40px', fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}>{Number.isFinite(metric.value) ? `${Math.round(metric.value!)}%` : '—'}</Typography>
        <LinearProgress aria-label={`${metric.name} usage`} variant="determinate" value={Number.isFinite(metric.value) ? Math.max(0, Math.min(100, metric.value!)) : 0}
          color={metric.value! > 90 ? 'error' : metric.value! > 80 ? 'warning' : 'primary'} sx={{ mt: 1, height: 8, borderRadius: 1, bgcolor: 'surface.track', visibility: Number.isFinite(metric.value) ? 'visible' : 'hidden' }} />
      </Panel>)}
      <ServiceCard span={8} title="Database" state={database} rows={[
        ['Database', databaseStatus?.database_name || 'Unavailable'],
        ['Server', databaseStatus?.server_name || 'Unavailable'],
        ['Connection mode', databaseStatus?.mode || 'Unavailable'],
      ]}>
        {databaseStatus?.error_message && <Alert severity="error" sx={{ m: 2, overflowWrap: 'anywhere' }}>{databaseStatus.error_message}</Alert>}
      </ServiceCard>
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
