import { useEffect, useState } from 'react';
import { Alert, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { api } from '../../services/api';
import ReportInputs, { changedInputs, requestMessage, type ReportField } from '../ReportInputs';
import StatusChip from '../StatusChip';
import type { PinnedPreparation, PreparationState, PreparationStep } from '../../types/scheduling';

type PreparationTool = { id: string; name: string; package_version: string; inputs: ReportField[]; setup_needed?: boolean; target?: string };

const stateChip: Record<PreparationState, { tone: 'completed' | 'attention' | 'fault' | 'neutral'; label: string }> = {
  ready: { tone: 'completed', label: 'Ready' },
  needs_review: { tone: 'attention', label: 'Needs review' },
  missing: { tone: 'fault', label: 'Not installed' },
  unknown: { tone: 'neutral', label: 'State unknown' },
};

/**
 * The schedule's database package step (kind "preparation"): uploaded Python that runs before
 * the method starts. `value` is undefined until the administrator changes it, so other edits
 * never send it and the server keeps the pinned step. Only a local administrator can edit.
 */
export default function PreparationStepField({ saved, state, value, onChange, editable }: {
  saved?: PinnedPreparation | null;
  state?: PreparationState;
  value: PreparationStep | null | undefined;
  onChange: (value: PreparationStep | null) => void;
  editable: boolean;
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
  const chip = saved && value === undefined && state ? <StatusChip {...stateChip[state]} /> : null;

  if (!editable) {
    return <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Typography variant="body2">
        Database step: {saved ? `${saved.tool_name ?? saved.tool_id} · v${saved.package_version}` : 'none'}
      </Typography>
      {chip}
      <Typography variant="caption" color="text.secondary">Only a local administrator can change this step.</Typography>
    </Stack>;
  }

  return <Stack spacing={1.5}>
    {error && <Alert severity="error">Database steps unavailable: {error}</Alert>}
    <Stack direction="row" spacing={1} alignItems="center">
      <TextField select size="small" fullWidth label="Database step" value={current?.tool_id ?? ''} disabled={!tools && !error}
        onChange={event => onChange(event.target.value ? { tool_id: event.target.value, inputs: {} } : null)}>
        <MenuItem value="">None</MenuItem>
        {saved && !tools?.some(candidate => candidate.id === saved.tool_id) && (
          <MenuItem value={saved.tool_id}>{saved.tool_name ?? saved.tool_id} · not installed</MenuItem>
        )}
        {(tools ?? []).map(candidate => (
          <MenuItem key={candidate.id} value={candidate.id} disabled={candidate.setup_needed}>
            {candidate.name} · v{candidate.package_version}{candidate.setup_needed ? ' · needs an operation connection' : ''}
          </MenuItem>
        ))}
      </TextField>
      {chip}
    </Stack>
    {state === 'needs_review' && value === undefined && (
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
