import { useEffect, useState } from 'react';
import { Alert, Box, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { api } from '../../services/api';
import ReportInputs, { changedInputs, requestMessage, type ReportField } from '../ReportInputs';
import StatusChip from '../StatusChip';
import type { LegacyPreparation, PinnedPreparation, PreparationState, PreparationStep, ScheduledExperiment } from '../../types/scheduling';

type PreparationTool = { id: string; name: string; package_version: string; inputs: ReportField[]; setup_needed?: boolean; target?: string };

export const stateChip: Record<PreparationState, { tone: 'completed' | 'attention' | 'fault' | 'neutral'; label: string }> = {
  ready: { tone: 'completed', label: 'Ready' },
  needs_review: { tone: 'attention', label: 'Needs review' },
  missing: { tone: 'fault', label: 'Not installed' },
  invalid: { tone: 'fault', label: 'Unreadable' },
  unknown: { tone: 'neutral', label: 'State unknown' },
};

/** One line for lists and details: the step's name, or why the run is held. */
export function preparationSummary(schedule: Pick<ScheduledExperiment, 'preparation' | 'legacy_preparation'>) {
  if (schedule.legacy_preparation) return 'Old EvoYeast selection · needs review';
  const step = schedule.preparation;
  return step ? `${step.tool_name ?? step.tool_id} · v${step.package_version}` : 'None';
}

/**
 * The schedule's database package step (kind "preparation"): uploaded Python that runs before
 * the method starts. `value` is undefined until the administrator changes it, so other edits
 * never send it and the server keeps the pinned step. Only a local administrator can edit.
 * `legacy` holds a schedule's retired adapter tokens: the form prefills `value` from its
 * suggestion so an administrator's save replaces them; until then the run is refused.
 */
export default function PreparationStepField({ saved, state, value, onChange, editable, legacy }: {
  saved?: PinnedPreparation | null;
  state?: PreparationState;
  value: PreparationStep | null | undefined;
  onChange: (value: PreparationStep | null) => void;
  editable: boolean;
  legacy?: LegacyPreparation | null;
}) {
  const current = value !== undefined ? value : saved ? { tool_id: saved.tool_id, inputs: saved.inputs } : null;
  const [tools, setTools] = useState<PreparationTool[] | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!editable) return;
    let live = true;
    api.get('/api/database/tools/catalogue', { params: { kind: 'preparation' } })
      .then(response => { if (live) { setTools(response.data); setError(''); } })
      .catch(cause => { if (live) setError(requestMessage(cause)); });
    return () => { live = false; };
  }, [editable]);
  const tool = tools?.find(candidate => candidate.id === current?.tool_id);
  const chip = state && (legacy || (saved && value === undefined)) ? <StatusChip {...stateChip[state]} /> : null;
  const legacyNotice = legacy && <Alert severity="warning">
    {legacy.message}
    <Typography variant="caption" component="div" sx={{ mt: 0.5, overflowWrap: 'anywhere' }}>Saved before: {legacy.steps.join(', ')}</Typography>
  </Alert>;

  if (!editable) {
    return <Stack spacing={1.5}>
      {legacyNotice}
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Typography variant="body2">
          Database step: {saved ? `${saved.tool_name ?? saved.tool_id} · v${saved.package_version}` : 'none'}
        </Typography>
        {chip}
        <Typography variant="caption" color="text.secondary">Only a local administrator can change this step.</Typography>
      </Stack>
    </Stack>;
  }

  return <Stack spacing={1.5}>
    {legacyNotice}
    {error && <Alert severity="error">Database steps unavailable: {error}</Alert>}
    <Stack direction="row" spacing={1} alignItems="center">
      <TextField select size="small" fullWidth label="Database step" value={current?.tool_id ?? ''} disabled={!tools && !error}
        onChange={event => onChange(event.target.value ? { tool_id: event.target.value, inputs: {} } : null)}>
        <MenuItem value="">None</MenuItem>
        {current && !tools?.some(candidate => candidate.id === current.tool_id) && (
          <MenuItem value={current.tool_id}>{saved?.tool_id === current.tool_id ? saved.tool_name ?? saved.tool_id : current.tool_id} · not installed</MenuItem>
        )}
        {(tools ?? []).map(candidate => (
          <MenuItem key={candidate.id} value={candidate.id} disabled={candidate.setup_needed}>
            {candidate.name} · v{candidate.package_version}{candidate.setup_needed ? ' · needs an operation connection' : ''}
          </MenuItem>
        ))}
      </TextField>
      {chip && <Box sx={{ flexShrink: 0 }}>{chip}</Box>}
    </Stack>
    {legacy && current && tools && !tool && (
      <Alert severity="info">Package {current.tool_id} is not installed. Install it in Database → Manage packages, assign its connections, then save this schedule.</Alert>
    )}
    {!legacy && state === 'needs_review' && value === undefined && (
      <Alert severity="warning">The package or its connection changed after this step was saved. Save the schedule to use the current version; until then the run does not start.</Alert>
    )}
    {tool && current && (
      <>
        {tool.inputs.length > 0 && (
          <ReportInputs fields={tool.inputs} values={current.inputs as Record<string, any>} disabled={false}
            choiceBase={`/api/database/tools/preparations/${tool.id}/choices`}
            onChange={(name, next) => onChange({ tool_id: tool.id, inputs: changedInputs(tool.inputs, current.inputs as Record<string, any>, name, next) })} />
        )}
        <Typography variant="caption" color="text.secondary">
          Runs before the method starts{tool.target ? `, writing to ${tool.target}` : ''}. If it fails or takes over two minutes, the run does not start and the schedule waits for recovery.
        </Typography>
      </>
    )}
  </Stack>;
}
