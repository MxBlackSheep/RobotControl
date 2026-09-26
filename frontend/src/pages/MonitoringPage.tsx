import React from 'react';
import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Card, CardContent, Chip, LinearProgress, Stack, Typography } from '@mui/material';
import ExpandMore from '@mui/icons-material/ExpandMore';
import Refresh from '@mui/icons-material/Refresh';
import { PageContent, PageHeader } from '../components/PageLayout';
import useMonitoring from '../hooks/useMonitoring';

export default function MonitoringPage() {
  // This page owns one monitoring request cycle. Presentation below never starts polling.
  const { monitoringData, systemHealth, databaseStatus, streamingStatus, isLoading, error, refreshData } = useMonitoring();
  const timestamp = systemHealth?.timestamp || monitoringData?.last_updated;
  const metrics = [
    { name: 'CPU', value: systemHealth?.cpu_percent },
    { name: 'Memory', value: systemHealth?.memory_percent, detail: systemHealth?.memory_total_gb != null ? `${systemHealth.memory_used_gb} / ${systemHealth.memory_total_gb} GB` : '' },
    { name: 'Disk', value: systemHealth?.disk_percent, detail: systemHealth?.disk_total_gb != null ? `${systemHealth.disk_used_gb} / ${systemHealth.disk_total_gb} GB` : '' },
  ];
  return <PageContent>
    <PageHeader title="System Status" actions={<>
      <Chip size="small" label={error ? monitoringData ? 'Stale data' : 'Unavailable' : isLoading ? 'Updating' : monitoringData ? 'Updated' : 'Unknown'} color={error ? 'warning' : 'default'} />
      <Button startIcon={<Refresh />} disabled={isLoading} onClick={() => void refreshData()}>Refresh</Button>
    </>} />
    {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}{monitoringData ? ' · Last reading retained.' : ''}</Alert>}
    {isLoading && <LinearProgress aria-label="Updating monitoring" sx={{ mb: 1 }} />}
    <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mb: 2 }}>
      <Chip label={databaseStatus ? databaseStatus.is_connected ? 'Database connected' : 'Database disconnected' : 'Database unavailable'} color={!databaseStatus || error ? 'default' : databaseStatus.is_connected ? 'success' : 'error'} />
      <Chip label={streamingStatus ? streamingStatus.enabled ? 'Streaming enabled' : 'Streaming disabled' : 'Streaming unavailable'} color={streamingStatus?.enabled && !error ? 'success' : 'default'} />
      {timestamp && <Typography variant="caption" sx={{ alignSelf: 'center', ml: 'auto' }} color="text.secondary">Last reading {new Date(timestamp).toLocaleString()}</Typography>}
    </Stack>
    <Typography variant="subtitle1" component="h2" sx={{ mb: 1 }}>Resource use</Typography>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 1.5, mb: 2 }}>
      {metrics.map(metric => <Card key={metric.name} variant="outlined"><CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline"><Typography component="h3" variant="subtitle1">{metric.name}</Typography><Typography variant="h5">{Number.isFinite(metric.value) ? `${Math.round(metric.value!)}%` : '—'}</Typography></Stack>
        {Number.isFinite(metric.value) && <LinearProgress aria-label={`${metric.name} usage`} variant="determinate" value={Math.max(0, Math.min(100, metric.value!))} color={metric.value! > 90 ? 'error' : metric.value! > 80 ? 'warning' : 'primary'} sx={{ mt: 1.5 }} />}
        {metric.detail && <Typography variant="caption" color="text.secondary">{metric.detail}</Typography>}
      </CardContent></Card>)}
    </Box>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' }, gap: 1.5, alignItems: 'start' }}>
      <Accordion disableGutters variant="outlined" defaultExpanded={!!databaseStatus?.error_message}>
        <AccordionSummary expandIcon={<ExpandMore />}><Typography>Database details</Typography></AccordionSummary>
        <AccordionDetails sx={{ overflowWrap: 'anywhere' }}>
          {databaseStatus ? <Stack gap={1}>
            <Typography>{databaseStatus.database_name} · {databaseStatus.server_name}</Typography>
            <Typography variant="body2" color="text.secondary">Mode: {databaseStatus.mode}</Typography>
            {databaseStatus.error_message && <Alert severity="error">{databaseStatus.error_message}</Alert>}
          </Stack> : <Typography color="text.secondary">Unavailable</Typography>}
        </AccordionDetails>
      </Accordion>
      <Accordion disableGutters variant="outlined">
        <AccordionSummary expandIcon={<ExpandMore />}><Typography>Streaming details</Typography></AccordionSummary>
        <AccordionDetails>
          {streamingStatus ? <Stack gap={1}>
            <Typography>Sessions: {streamingStatus.active_session_count ?? '—'} / {streamingStatus.max_sessions ?? '—'}</Typography>
            <Typography>Bandwidth: {streamingStatus.total_bandwidth_mbps != null ? `${streamingStatus.total_bandwidth_mbps.toFixed(1)} Mb/s` : '—'}</Typography>
            <Typography>Utilization: {streamingStatus.resource_usage_percent != null ? `${Math.round(streamingStatus.resource_usage_percent)}%` : '—'}</Typography>
          </Stack> : <Typography color="text.secondary">Unavailable</Typography>}
        </AccordionDetails>
      </Accordion>
    </Box>
  </PageContent>;
}
