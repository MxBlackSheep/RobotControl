import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Card, CardContent, Chip, LinearProgress, Stack, Typography } from '@mui/material';
import ExpandMore from '@mui/icons-material/ExpandMore';
import Refresh from '@mui/icons-material/Refresh';
import { PageContent, PageHeader } from '../components/PageLayout';
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
  return <PageContent variant="overview">
    <PageHeader title="System Status" actions={<>
      <Chip size="small" label={error ? monitoringData ? 'Stale data' : 'Unavailable' : isLoading ? 'Updating' : monitoringData ? 'Updated' : 'Unknown'} color={error ? 'warning' : 'default'} />
      <Button startIcon={<Refresh />} disabled={isLoading} onClick={() => void refreshData()}>Refresh</Button>
    </>} />
    {error && <Alert severity="warning" sx={{ mb: 1 }}>{error}{monitoringData ? ' · Last reading retained.' : ''}</Alert>}
    {isLoading && <LinearProgress aria-label="Updating monitoring" sx={{ mb: 1 }} />}
    <Stack direction="row" gap={1} flexWrap="wrap" sx={{ mb: 2 }}>
      <Chip label={databaseStatus?.is_connected === true ? 'Database connected' : databaseStatus?.is_connected === false ? 'Database disconnected' : 'Database unavailable'} color={error ? 'default' : databaseStatus?.is_connected === true ? 'success' : databaseStatus?.is_connected === false ? 'error' : 'default'} />
      <Chip label={streamingStatus?.enabled === true ? 'Live view enabled' : streamingStatus?.enabled === false ? 'Live view disabled' : 'Live view unavailable'} />
      {timestamp && <Typography variant="caption" sx={{ alignSelf: 'center', ml: 'auto' }} color="text.secondary">Last reading {new Date(timestamp).toLocaleString()}</Typography>}
    </Stack>
    {databaseStatus?.error_message && <Alert severity="error" sx={{ mb: 2, overflowWrap: 'anywhere' }}>{databaseStatus.error_message}</Alert>}
    <Typography variant="subtitle1" component="h2" sx={{ mb: 1 }}>Resource use</Typography>
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 1.5, mb: 2 }}>
      {metrics.map(metric => <Card key={metric.name} variant="outlined"><CardContent>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline"><Typography component="h3" variant="subtitle1">{metric.name}</Typography><Typography variant="h5">{Number.isFinite(metric.value) ? `${Math.round(metric.value!)}%` : '—'}</Typography></Stack>
        {Number.isFinite(metric.value) && <LinearProgress aria-label={`${metric.name} usage`} variant="determinate" value={Math.max(0, Math.min(100, metric.value!))} color={metric.value! > 90 ? 'error' : metric.value! > 80 ? 'warning' : 'primary'} sx={{ mt: 1.5 }} />}
        {metric.detail && <Typography variant="caption" color="text.secondary">{metric.detail}</Typography>}
      </CardContent></Card>)}
    </Box>
    <Accordion disableGutters variant="outlined">
      <AccordionSummary id="connection-details-heading" aria-controls="connection-details-content" expandIcon={<ExpandMore />}>
        <Typography>Connection details</Typography>
      </AccordionSummary>
      <AccordionDetails id="connection-details-content" sx={{ overflowWrap: 'anywhere' }}>
        <Box component="dl" sx={{ m: 0, display: 'grid', gridTemplateColumns: 'minmax(100px, 1fr) minmax(0, 3fr)', gap: 1, '& dt': { color: 'text.secondary' }, '& dd': { m: 0, minWidth: 0 } }}>
          <Typography component="dt" variant="body2">Database</Typography>
          <Typography component="dd" variant="body2">{databaseStatus?.database_name || 'Unavailable'}</Typography>
          <Typography component="dt" variant="body2">Server</Typography>
          <Typography component="dd" variant="body2">{databaseStatus?.server_name || 'Unavailable'}</Typography>
          <Typography component="dt" variant="body2">Connection mode</Typography>
          <Typography component="dd" variant="body2">{databaseStatus?.mode || 'Unavailable'}</Typography>
          <Typography component="dt" variant="body2">Live view sessions</Typography>
          <Typography component="dd" variant="body2">{sessionSummary}</Typography>
        </Box>
      </AccordionDetails>
    </Accordion>
  </PageContent>;
}
