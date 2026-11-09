import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, Stack, Typography } from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import { DetailTitle, EmptyPanel, ListRow, PageContent, PageGrid, PageHeader, Panel } from '../components/PageLayout';
import StatusChip from '../components/StatusChip';
import { api } from '../services/api';
import { useSerialPolling } from '../hooks/useSerialPolling';
import { usePyHslStatus } from '../hooks/usePyHslStatus';
import { fontMono, type StatusTone } from '../theme';
import { clockTime } from '../utils/displayTime';

type Run = {
  run_id: string; protocol: string; status: string; host_status: string | null; mode: string | null;
  completed_count: number | null; error: string | null; origin: string | null; created_at: string | null; updated_at: string | null;
  protocol_revision: string | null; current: { operation: string | null; status: string | null } | null;
  prompt: { waiting: boolean; text: string | null }; requires_review: boolean | null;
};
type Step = { revision: number; at: string | null; event: string; text: string | null };

const ENDED = ['completed', 'failed', 'stopped', 'outcome_unknown', 'reconciliation_required'];
const label = (text: string) => text.charAt(0).toUpperCase() + text.slice(1).replace(/_/g, ' ');
const mono = { fontFamily: fontMono, fontSize: 12, color: 'text.secondary' } as const;

function statusTone(status: string): StatusTone {
  if (status === 'completed') return 'completed';
  if (status === 'stopped') return 'neutral';
  return ENDED.includes(status) ? 'fault' : 'running';
}

function Fact({ name, value }: { name: string; value: string }) {
  return <Stack direction="row" justifyContent="space-between" gap={2} sx={{ fontSize: 13 }}>
    <Box component="span" sx={{ color: 'text.secondary' }}>{name}</Box>
    <Box component="span" sx={{ textAlign: 'right', overflowWrap: 'anywhere' }}>{value}</Box>
  </Stack>;
}

/**
 * A read-only view of one PyHSL run, relayed through the backend. Actions stay in Run Control on
 * the robot PC. A failed read keeps the last reading and says since when it is old.
 */
export default function PyHslRunPage() {
  const [params] = useSearchParams();
  const status = usePyHslStatus();
  const runId = params.get('run') || status?.run?.run_id || null;
  const [run, setRun] = useState<Run | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [readAt, setReadAt] = useState<Date | null>(null);
  const after = useRef(0);
  const [report, setReport] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);

  useEffect(() => { after.current = 0; setRun(null); setSteps([]); setReport(null); setReportError(null); setReadAt(null); }, [runId]);

  const polling = useSerialPolling<{ run: Run; events: Step[]; next: number }>({
    enabled: !!runId,
    identity: runId,
    interval: 5000,
    request: async signal => {
      const [state, journal] = await Promise.all([
        api.get(`/api/pyhsl/runs/${runId}`, { signal }),
        api.get(`/api/pyhsl/runs/${runId}/journal`, { params: { after: after.current, limit: 200 }, signal }),
      ]);
      return { run: state.data, events: journal.data.events, next: journal.data.next };
    },
    onSuccess: value => {
      setRun(value.run);
      setReadAt(new Date());
      after.current = value.next;
      if (value.events.length) setSteps(previous => [...previous, ...value.events]);
    },
  });

  const showReport = useCallback(async () => {
    setReportError(null);
    try {
      setReport((await api.get(`/api/pyhsl/runs/${runId}/report`, { responseType: 'text' })).data);
    } catch (err: any) {
      setReportError(err?.response?.data?.detail || 'Could not load the report');
    }
  }, [runId]);

  if (!runId) return <PageContent>
    <PageHeader title="PyHSL run" />
    <EmptyPanel title="Run">No run is active.</EmptyPanel>
  </PageContent>;

  const ended = !!run && ENDED.includes(run.status);
  const shown = steps.filter(step => step.text).slice(-200).reverse();
  return <PageContent>
    <PageHeader title={run?.protocol || 'PyHSL run'} />
    <PageGrid>
      {polling.error && <Box sx={{ gridColumn: '1 / -1' }}>
        <Alert severity="warning">{readAt ? `Run Control not reachable since ${clockTime(readAt)}.` : 'Run Control not reachable.'}</Alert>
      </Box>}
      <Panel title="Run" span={5} headerExtra={run && <StatusChip tone={polling.error ? 'neutral' : statusTone(run.status)} label={polling.error ? 'Unknown' : label(run.status)} />}
        bodySx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
        {!run && !polling.error && <Typography variant="body2" color="text.secondary">Loading</Typography>}
        {run && <>
          <DetailTitle component="p">{run.protocol}</DetailTitle>
          {run.mode && <Fact name="Mode" value={label(run.mode)} />}
          {typeof run.completed_count === 'number' && <Fact name="Done" value={String(run.completed_count)} />}
          {run.created_at && <Fact name="Started" value={clockTime(new Date(run.created_at))} />}
          {!ended && run.current?.operation && <Fact name="Now" value={label(run.current.operation)} />}
          {run.origin === 'machine' && <Fact name="Started by" value="Schedule" />}
          {run.prompt?.waiting && <Alert severity="warning" sx={{ overflowWrap: 'anywhere' }}>{run.prompt.text || 'Waiting for an answer.'} Answer it in Run Control on the robot PC.</Alert>}
          {run.requires_review && <Alert severity="warning">Record the Run review in Run Control on the robot PC.</Alert>}
          {ended && run.requires_review === null && <Alert severity="warning">Run review state unknown.</Alert>}
          {run.error && <Alert severity="error" sx={{ overflowWrap: 'anywhere' }}>{run.error}</Alert>}
          {ended && !report && <Button variant="outlined" onClick={() => void showReport()} sx={{ alignSelf: 'flex-start' }}>Show report</Button>}
          {reportError && <Alert severity="error">{reportError}</Alert>}
        </>}
      </Panel>
      <Panel title="Steps" span={7} inset={false} sx={{ maxHeight: 520, overflow: 'auto' }}>
        {!shown.length && <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>No steps yet.</Typography>}
        {shown.map(step => <ListRow key={step.revision} columns="64px minmax(0, 1fr)">
          <Box component="span" sx={mono}>{step.at ? clockTime(new Date(step.at)) : ''}</Box>
          <Box component="span">{step.text}</Box>
        </ListRow>)}
      </Panel>
      {report !== null && <Panel title="Report" inset={false}>
        {/* An empty sandbox: PyHSL's report runs no script and reaches nothing of RobotControl. */}
        <iframe title="PyHSL report" sandbox="" srcDoc={report} style={{ width: '100%', height: 640, border: 0, display: 'block' }} />
      </Panel>}
    </PageGrid>
  </PageContent>;
}
