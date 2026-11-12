import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Box, Button, Dialog, DialogContent, DialogTitle } from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import { EmptyPanel, PageContent, PageHeader } from '../components/PageLayout';
import PyHslMonitor, { type MonitorView } from '../components/PyHslMonitor';
import { useLabwareWorkspace } from '../components/labware/useLabwareWorkspace';
import { api } from '../services/api';
import { appErrorMessage } from '../services/requestError';
import { useSerialPolling } from '../hooks/useSerialPolling';
import { usePyHslStatus } from '../hooks/usePyHslStatus';
import { layout } from '../theme';
import { clockTime } from '../utils/displayTime';

/** Run Control's run body, passed to the view as received; the page itself reads only its status. */
type Run = { status: string } & Record<string, unknown>;

const ENDED = ['completed', 'failed', 'stopped', 'outcome_unknown', 'reconciliation_required'];

/**
 * A read-only view of one PyHSL run. PyHSL's own Run view (status, deck, transport and current step, without
 * controls) fills the window; RobotControl adds only the title, reachability and the report. Actions stay in
 * Run Control. A failed read keeps the last reading and says since when it is old.
 */
export default function PyHslRunPage() {
  const [params] = useSearchParams();
  const status = usePyHslStatus();
  const latest = useRef<string | null>(null);
  if (status?.run) latest.current = status.run.run_id;
  const runId = params.get('run') || latest.current;
  const [run, setRun] = useState<Run | null>(null);
  // Kept with the run it was read for, so a different run never borrows it.
  const [deck, setDeck] = useState<{ run: string; body: unknown } | null>(null);
  const [deckError, setDeckError] = useState<string | null>(null);
  const [readAt, setReadAt] = useState<Date | null>(null);
  const [report, setReport] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const workspace = useLabwareWorkspace(!!runId);

  // A new object only when a body changed, so the view redraws once per reading.
  const view = useMemo<MonitorView | null>(() => deck && run ? { deck: deck.body, state: run } : null, [deck, run]);

  useEffect(() => { setRun(null); setDeck(null); setDeckError(null); setReport(null); setReportError(null); setReadAt(null); }, [runId]);

  const polling = useSerialPolling<{ run: Run; deck: typeof deck; deckError: string | null }>({
    enabled: !!runId,
    identity: runId,
    interval: run && ENDED.includes(run.status) ? 30000 : 5000,
    request: async signal => {
      const state = (await api.get(`/api/pyhsl/runs/${runId}`, { signal })).data;
      // The deck body is large and fixed for a run: read once per run, after the run itself was read, and
      // again only after a failure. A failed deck read shows in the view's place; the title and report stay usable.
      if (deck?.run === runId) return { run: state, deck, deckError: null };
      try {
        return { run: state, deck: { run: runId!, body: (await api.get('/api/pyhsl/deck', { signal })).data }, deckError: null };
      } catch (err: any) {
        if (signal.aborted) throw err;
        return { run: state, deck: null, deckError: appErrorMessage(err) || 'PyHSL did not answer' };
      }
    },
    onSuccess: value => { setRun(value.run); setDeck(value.deck); setDeckError(value.deckError); setReadAt(new Date()); },
  });

  const showReport = useCallback(async () => {
    setReportError(null);
    try {
      setReport((await api.get(`/api/pyhsl/runs/${runId}/report`, { responseType: 'text' })).data);
    } catch (err: any) {
      setReportError(appErrorMessage(err) || 'Could not load the report');
    }
  }, [runId]);

  if (!runId) return <PageContent>
    <PageHeader title="PyHSL run" />
    <EmptyPanel title="Run">{status?.state === 'running' ? 'No run is active.' : status?.state === 'not_running' ? 'PyHSL is not running.' : 'PyHSL state is unknown.'}</EmptyPanel>
  </PageContent>;

  const ended = !!run && ENDED.includes(run.status);
  return <PageContent>
    <PageHeader title="PyHSL run"
      actions={ended && <Button variant="outlined" onClick={() => void showReport()}>Show report</Button>} />
    {/* Always present, so the fit below is measured again when a line appears or goes. */}
    <Box sx={{ '& > *': { mb: `${layout.gutter}px` } }}>
      {polling.error && <Alert severity="warning">{readAt ? `Run Control not reachable since ${clockTime(readAt)}.` : 'Run Control not reachable.'}</Alert>}
      {reportError && <Alert severity="error">{reportError}</Alert>}
    </Box>
    {/* The view fits the rest of the window and scrolls its own panels; the page itself does not scroll. */}
    <Box ref={workspace.ref} sx={{ minWidth: 0, height: workspace.height ? `${Math.max(480, workspace.height)}px` : 480 }}>
      <PyHslMonitor view={view} error={deckError} />
    </Box>
    <Dialog open={report !== null} onClose={() => setReport(null)} fullWidth maxWidth="xl">
      <DialogTitle>Report</DialogTitle>
      <DialogContent sx={{ p: 0 }}>
        {/* An empty sandbox: PyHSL's report runs no script and reaches nothing of RobotControl. */}
        <iframe title="PyHSL report" sandbox="" srcDoc={report ?? ''} style={{ width: '100%', height: '80vh', border: 0, display: 'block' }} />
      </DialogContent>
    </Dialog>
  </PageContent>;
}
