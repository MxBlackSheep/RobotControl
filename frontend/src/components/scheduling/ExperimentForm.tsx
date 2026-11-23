import { useRef, useState } from 'react';
import { Alert, Box, Button, FormControlLabel, Stack, Switch, TextField, Typography } from '@mui/material';
import { Panel } from '../PageLayout';
import { api } from '../../services/api';
import { requestMessage, toolsBase } from '../ReportInputs';
import ExperimentPlateGrid, { recentLayout, wells } from './ExperimentPlateGrid';

const defaults: Record<string, string> = {
  TargetWellVolume:'700', MaxIteration:'20', TopFractionToPropagate:'1',
  BackgroundOD:'0.036', InoculationOD:'0.03', ODConversionFactor:'2.52', FreezeVolume:'0.5',
  V_OD_Sample:'150', FreezeGeneration:'1', UseFluorescence:'1', GFP_scale:'4669.1',
  GFP_RFPdamping:'773.1', RFP_scale:'2262.3', RFP_GFPdamping:'305.0',
};
export default function ExperimentForm() {
  const [userId, setUserId] = useState(''), [note, setNote] = useState('');
  const [schedule, setSchedule] = useState(false), [parameters, setParameters] = useState({...defaults});
  const [layout, setLayout] = useState(recentLayout), [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{severity:'error'|'warning'|'success'; text:string} | null>(null);
  const attempt = useRef<{body:string; token:string} | null>(null);
  const submit = async () => {
    if (busy) return;
    setMessage(null);
    if (!userId.trim()) { setMessage({severity:'error', text:'Enter an experiment ID.'}); return; }
    const numbers: Record<string, number> = {};
    for (const [name, value] of Object.entries(parameters)) {
      if (!value.trim() || !Number.isFinite(Number(value))) { setMessage({severity:'error', text:`${name} must be a finite number.`}); return; }
      numbers[name] = Number(value);
    }
    if (![0.25,0.5,1].includes(numbers.TopFractionToPropagate)) { setMessage({severity:'error', text:'TopFractionToPropagate must be 0.25, 0.5 or 1 (25%, 50% or 100%).'}); return; }
    if (!Object.values(layout).includes('Cells')) { setMessage({severity:'error', text:'Mark at least one culture well.'}); return; }
    const body = {user_id:userId.trim(), note:note.trim(), schedule:schedule ? 1 : 0, parameters:numbers,
      layout:wells.filter(w => layout[w]).map(w => [w,layout[w]])};
    const serialized = JSON.stringify(body);
    if (attempt.current?.body !== serialized) attempt.current = {body:serialized, token:crypto.randomUUID().replace(/-/g,'')};
    setBusy(true);
    try {
      const {data} = await api.post(`${toolsBase}/experiments`, {...body, token:attempt.current!.token});
      if (data.status === 'succeeded') {
        setMessage({severity:'success', text:`Experiment ${data.result.experiment_id} registered.${data.warning ? ` ${data.warning}` : ''}`});
        setUserId(''); setNote(''); setSchedule(false); setParameters({...defaults}); setLayout(recentLayout()); attempt.current = null;
      } else {
        setMessage({severity:data.status === 'unknown' ? 'warning' : 'error', text:data.message});
        if (data.status === 'error') attempt.current = null;
      }
    } catch (error: any) {
      const refused = error.response && error.response.status < 500;
      setMessage({severity:refused ? 'error' : 'warning', text:refused ? requestMessage(error) : `Outcome unknown. Check whether experiment ${userId.trim()} exists before trying again.`});
      if (refused) attempt.current = null;
    } finally { setBusy(false); }
  };
  const fields = (names: string[]) => <Box sx={{display:'grid', gridTemplateColumns:{xs:'1fr', sm:'repeat(3, minmax(0, 1fr))'}, gap:2}}>
    {names.map(name => <TextField key={name} label={name} value={parameters[name]} onChange={e => setParameters({...parameters,[name]:e.target.value})} disabled={busy} size="small" />)}
  </Box>;
  return <Panel title="Experiments"><Box component="form" onSubmit={e => { e.preventDefault(); void submit(); }} sx={{p:2, maxWidth:1000}}>
    <Stack spacing={2}>
      {message && <Alert severity={message.severity}>{message.text}</Alert>}
      <TextField label="Experiment ID" value={userId} onChange={e => setUserId(e.target.value)} disabled={busy} inputProps={{maxLength:255}} />
      <TextField label="Note" value={note} onChange={e => setNote(e.target.value)} disabled={busy} multiline inputProps={{maxLength:4000}} />
      <FormControlLabel control={<Switch checked={schedule} onChange={e => setSchedule(e.target.checked)} disabled={busy} />} label="Schedule now" />
      {fields(Object.keys(defaults).slice(0,3))}
      <Box component="details"><Typography component="summary" sx={{cursor:'pointer', mb:2}}>More parameters</Typography>{fields(Object.keys(defaults).slice(3))}</Box>
      <ExperimentPlateGrid value={layout} onChange={setLayout} disabled={busy} />
      <Button type="submit" variant="contained" disabled={busy} sx={{alignSelf:'flex-start'}}>Register</Button>
    </Stack>
  </Box></Panel>;
}
