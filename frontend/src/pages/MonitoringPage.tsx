import React from 'react';
import { Alert, Box, Button, Card, CardContent, LinearProgress, Stack, Typography } from '@mui/material';
import StatusChip from '../components/StatusChip';
import { fontMono } from '../theme';
import Refresh from '@mui/icons-material/Refresh';
import { PageContent, PageHeader, PanelHeader, PanelLabel } from '../components/PageLayout';
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
      <Button startIcon={<Refresh />} disabled={isLoading} onClick={() => void refreshData()}>Refresh</Button>
    </>} />
    {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}{monitoringData ? ' · Last reading retained.' : ''}</Alert>}
    {isLoading && <LinearProgress aria-label="Updating monitoring" sx={{ mb: 1 }} />}
    <Stack direction="row" alignItems="baseline" justifyContent="space-between" gap={1} flexWrap="wrap" sx={{ mb: 1 }}>
      <PanelLabel>Resource use</PanelLabel>
      {timestamp && <Typography variant="caption" color="text.secondary">Last reading {new Date(timestamp).toLocaleString()}</Typography>}
    </Stack>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 2, mb: 2 }}>
      {metrics.map(metric => <Card key={metric.name} variant="outlined"><CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
          <Typography component="h3" sx={{ fontSize: 15, fontWeight: 600 }}>{metric.name}</Typography>
          <Typography sx={{ fontFamily: fontMono, fontSize: 30, fontWeight: 600, lineHeight: 1.2 }}>{Number.isFinite(metric.value) ? `${Math.round(metric.value!)}%` : '—'}</Typography>
        </Stack>
        {Number.isFinite(metric.value) && <LinearProgress aria-label={`${metric.name} usage`} variant="determinate" value={Math.max(0, Math.min(100, metric.value!))} color={metric.value! > 90 ? 'error' : metric.value! > 80 ? 'warning' : 'primary'} sx={{ mt: 1.5, height: 8, borderRadius: 4 }} />}
        {metric.detail && <Typography sx={{ mt: 1, fontSize: 13, color: 'text.secondary' }}>{metric.detail}</Typography>}
      </CardContent></Card>)}
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, gap: 2, alignItems: 'start' }}>
      <ServiceCard title="Database" state={database} rows={[
        ['Database', databaseStatus?.database_name || 'Unavailable'],
        ['Server', databaseStatus?.server_name || 'Unavailable'],
        ['Connection mode', databaseStatus?.mode || 'Unavailable'],
      ]}>
        {databaseStatus?.error_message && <Alert severity="error" sx={{ mt: 1.5, overflowWrap: 'anywhere' }}>{databaseStatus.error_message}</Alert>}
      </ServiceCard>
      <ServiceCard title="Live view" state={liveView} rows={[['Sessions', sessionSummary]]} />
    </Box>
  </PageContent>;
}

function ServiceCard({ title, state: [label, tone], rows, children }: { title: string; state: [string, StatusTone]; rows: [string, string][]; children?: React.ReactNode }) {
  return <Card component="section" aria-label={title} variant="outlined"><CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <PanelHeader title={title} actions={<StatusChip tone={tone} label={label} />} />
    <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: 'minmax(110px, auto) minmax(0, 1fr)', columnGap: 2, rowGap: 1, fontSize: 14, '& dt': { color: 'text.secondary' }, '& dd': { m: 0, minWidth: 0, overflowWrap: 'anywhere' } }}>
      {rows.map(([name, value]) => <React.Fragment key={name}><Typography component="dt" variant="body2">{name}</Typography><Typography component="dd" variant="body2">{value}</Typography></React.Fragment>)}
    </Box>
    {children}
  </CardContent></Card>;
}
