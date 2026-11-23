import { cloneElement, useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Alert, Box, Button, FormControlLabel, MenuItem, Stack, Switch, TextField, Typography, useMediaQuery } from '@mui/material';
import { Link } from 'react-router-dom';
import { Panel } from '../PageLayout';
import { layout as spacing } from '../../theme';
import { api, currentSignIn } from '../../services/api';
import { requestMessage, toolsBase } from '../ReportInputs';
import ExperimentPlateGrid, { PlateAssignment, PlateLayout, wells } from './ExperimentPlateGrid';

import { evaluateLayoutRule, LayoutRule } from './experimentLayoutRules';
import type { PreparationStep } from '../../types/scheduling';

type Parameter = {name:string; label:string; type:'number'|'integer'|'text'|'choice'; default:string|number;
  min?:number; max?:number; allowed?:(string|number)[]; group:'main'|'more'; fixed?:boolean};
type ExperimentType = {id:string; name:string; package_id:string; package_version:string; sha256:string; parameters:Parameter[];
  layout?:{kind:'plate96'; assignments:PlateAssignment[]; default:[string,string][]; required:string[]; rules?:LayoutRule[]}};
const defaults = (type:ExperimentType) => Object.fromEntries(type.parameters.map(p => [p.name, String(p.default)]));
const defaultLayout = (type:ExperimentType):PlateLayout => Object.fromEntries(type.layout?.default ?? []);
type Message = {severity:'error'|'warning'|'success'; text:string} | null;
type Attempt = {body:string; token:string; warned?:boolean};
type Draft = {definition:ExperimentType; userDefinedId:string; note:string; schedule:boolean; parameters:Record<string,string>; layout:PlateLayout;
  experimentId?:number; message:Message; attempts:Attempt[]; busy:boolean; stale:boolean};
const freshDraft = (definition:ExperimentType):Draft => ({definition, userDefinedId:'', note:'', schedule:false,
  parameters:defaults(definition), layout:defaultLayout(definition), message:null, attempts:[], busy:false, stale:false});
// Session drafts include the reviewed definition and unresolved token, and survive section navigation.
const drafts = new Map<string,Draft>();
const listeners = new Set<() => void>();
const subscribe = (listener:() => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
let selectedType = '';
let draftSignIn = currentSignIn();
export default function ExperimentForm({onOpenScheduling}:{onOpenScheduling:(preparation:PreparationStep)=>void}) {
  if (draftSignIn !== currentSignIn()) {
    drafts.clear(); selectedType = ''; draftSignIn = currentSignIn();
  }
  const [types, setTypes] = useState<ExperimentType[] | null>(null);
  const [loadError, setLoadError] = useState('');
  const [typeId, setTypeId] = useState(selectedType);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const signIn = currentSignIn();
    const reloadingType = revision ? selectedType : '';
    setLoadError('');
    api.get<ExperimentType[]>(`${toolsBase}/experiments/types`, {signal:controller.signal}).then(({data}) => {
      if (controller.signal.aborted || signIn !== currentSignIn()) return;
      setTypes(data);
      for (const definition of data) {
        const draft = drafts.get(definition.id);
        if (definition.id === reloadingType && draft && !draft.busy) {
          drafts.set(definition.id, {...freshDraft(definition), attempts:draft.attempts});
          listeners.forEach(listener => listener());
        }
      }
      if (!selectedType && data.length === 1) { selectedType = data[0].id; setTypeId(selectedType); }
    }).catch(error => { if (!controller.signal.aborted && signIn === currentSignIn()) setLoadError(requestMessage(error)); });
    return () => controller.abort();
  }, [revision]);
  const chooseType = (id:string) => { selectedType = id; setTypeId(id); };
  const reload = () => setRevision(value => value + 1);
  const installed = types?.find(t => t.id === typeId);
  const type = installed ?? drafts.get(typeId)?.definition;
  const choices = [...(types ?? []), ...Array.from(drafts.values(), draft => draft.definition).filter(definition => !types?.some(t => t.id === definition.id))];
  const picker = choices.length > 1 ? <TextField select label="Experiment type" value={type ? typeId : ''}
    onChange={e => chooseType(e.target.value)} fullWidth disabled={drafts.get(typeId)?.busy}>
    {choices.map(t => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
  </TextField> : null;
  if (loadError && !type) return <Alert severity="error" action={<Button color="inherit" onClick={reload}>Reload types</Button>}>{loadError}</Alert>;
  if (!types && !loadError) return <Panel title="Experiments"><Typography color="text.secondary">Loading experiment types...</Typography></Panel>;
  if (!type) return <Panel title="Experiments"><Stack spacing={2} alignItems="flex-start">
    {typeId && <Alert severity="error">Experiment type is no longer installed. Its draft is kept.</Alert>}
    {choices.length ? <>{picker ?? <Button onClick={() => chooseType(choices[0].id)}>{choices[0].name}</Button>}<Typography color="text.secondary">Choose an experiment type.</Typography></> : <>
      <Typography color="text.secondary">No experiment types installed.</Typography>
      <Button component={Link} to="/database?section=packages" variant="outlined">Manage packages</Button>
    </>}
    <Button onClick={reload}>Reload types</Button>
  </Stack></Panel>;
  return <ExperimentDraft key={type.id} installed={type} removed={types !== null && !installed} loadError={loadError} picker={picker} reload={reload} onOpenScheduling={onOpenScheduling} />;
}
function ExperimentDraft({installed, removed, loadError, picker, reload, onOpenScheduling}:{installed:ExperimentType; removed:boolean; loadError:string; picker:React.ReactNode; reload:()=>void; onOpenScheduling:(preparation:PreparationStep)=>void}) {
  if (!drafts.has(installed.id)) drafts.set(installed.id, freshDraft(installed));
  const draft = useSyncExternalStore(subscribe, () => drafts.get(installed.id)!);
  const signIn = currentSignIn();
  const update = (patch:Partial<Draft>) => {
    if (signIn !== currentSignIn()) return;
    drafts.set(installed.id, {...drafts.get(installed.id)!, ...patch});
    listeners.forEach(listener => listener());
  };
  const {definition:type, userDefinedId, note, schedule, parameters, layout, message, busy} = draft;
  const [active, setActive] = useState<{experiment_id:number; user_defined_id:string}[] | null>(null);
  const [activeError, setActiveError] = useState('');
  const [handoffError, setHandoffError] = useState('');
  const [opening, setOpening] = useState(false);
  const handoff = useRef<AbortController | null>(null);
  useEffect(() => () => handoff.current?.abort(), []);
  useEffect(() => {
    if (!schedule) return;
    const controller = new AbortController();
    setActive(null); setActiveError('');
    api.get(`${toolsBase}/experiments/active`, {signal:controller.signal})
      .then(({data}) => { if (!controller.signal.aborted) setActive(data); })
      .catch(error => { if (!controller.signal.aborted) setActiveError(requestMessage(error)); });
    return () => controller.abort();
  }, [schedule]);
  const openScheduling = async () => {
    handoff.current?.abort();
    const controller = new AbortController();
    handoff.current = controller;
    setOpening(true); setHandoffError('');
    try {
      const {data} = await api.get<PreparationStep>(`${toolsBase}/experiments/${draft.experimentId}/schedule-draft`, {signal:controller.signal});
      if (!controller.signal.aborted) onOpenScheduling(data);
    } catch (error) { if (!controller.signal.aborted) setHandoffError(`Scheduling setup needed: ${requestMessage(error)}`); }
    finally { if (!controller.signal.aborted) setOpening(false); }
  };
  const stale = removed || draft.stale || type.sha256 !== installed.sha256 || type.package_version !== installed.package_version;
  const setUserDefinedId = (userDefinedId:string) => update({userDefinedId});
  const setNote = (note:string) => update({note});
  const setSchedule = (schedule:boolean) => update({schedule});
  const setParameters = (parameters:Record<string,string>) => update({parameters});
  const setLayout = (layout:PlateLayout) => update({layout});
  const setMessage = (message:Message) => update({message});
  const wide = useMediaQuery('(min-width:1280px)');
  const showAllParameters = wide && type.parameters.length <= 12;
  const ruleResults = (type.layout?.rules ?? []).map(rule => evaluateLayoutRule(rule, parameters[rule.parameter] ?? '', layout, type.layout!.assignments));
  const ruleFailure = ruleResults.find(result => !result.valid)?.reason;
  const summary = type.layout?.assignments.map(a => {
    const count = Object.values(layout).filter(value => value === a.value).length;
    return `${count} ${a.label.toLowerCase()}${count === 1 ? '' : 's'}`;
  }).join(', ');
  const submit = async () => {
    if (drafts.get(installed.id)!.busy || opening || stale || loadError || ruleFailure) return;
    setMessage(null);
    const refuse = (text:string) => setMessage({severity:'error', text});
    if (!userDefinedId.trim()) { refuse('Enter a UserDefinedID.'); return; }
    const values: Record<string, string|number> = {};
    for (const field of type.parameters) {
      const raw = field.fixed ? String(field.default) : parameters[field.name] ?? '';
      const numeric = field.type === 'number' || field.type === 'integer';
      const value = numeric ? Number(raw) : field.allowed?.find(v => String(v) === raw) ?? raw;
      if (numeric && (!raw.trim() || !Number.isFinite(value) || (field.type === 'integer' && !Number.isInteger(value)))) {
        refuse(`${field.label} must be ${field.type === 'integer' ? 'a whole' : 'a finite'} number.`); return;
      }
      if (typeof value === 'number' && ((field.min != null && value < field.min) || (field.max != null && value > field.max))) {
        refuse(`${field.label} must be ${field.min != null && field.max != null ? `between ${field.min} and ${field.max}` : field.min != null ? `at least ${field.min}` : `at most ${field.max}`}.`); return;
      }
      if (!numeric && (!raw.trim() || raw.length > 255)) { refuse(`${field.label} must contain 1 to 255 characters.`); return; }
      if (field.allowed && !field.allowed.includes(value)) { refuse(`Choose a valid ${field.label.toLowerCase()}.`); return; }
      values[field.name] = value;
    }
    for (const assignment of type.layout?.required ?? []) {
      if (!Object.values(layout).includes(assignment)) { refuse(`Mark at least one ${type.layout?.assignments.find(a => a.value === assignment)?.label ?? assignment} well.`); return; }
    }
    const body = {type_id:type.id, package_version:type.package_version, sha256:type.sha256,
      user_defined_id:userDefinedId.trim(), note:note.trim(), schedule:schedule ? 1 : 0, parameters:values,
      ...(type.layout ? {layout:wells.filter(w => layout[w]).map(w => [w,layout[w]])} : {})};
    const serialized = JSON.stringify(body);
    const attempts = drafts.get(installed.id)!.attempts;
    const matching = attempts.find(attempt => attempt.body === serialized);
    const previous = attempts[attempts.length - 1];
    if (!matching && previous && !previous.warned) {
      update({attempts:attempts.map(attempt => attempt === previous ? {...attempt, warned:true} : attempt),
        message:{severity:'warning', text:`Previous outcome unknown. ${unknownMessage(previous)}`}});
      return;
    }
    await sendAttempt(matching ?? {body:serialized, token:crypto.randomUUID().replace(/-/g,'')}, true);
  };
  const unknownMessage = (attempt:Attempt) => `Check UserDefinedID '${JSON.parse(attempt.body).user_defined_id}', its experiment row, parameters and any plate layout in the database before trying again.`;
  const sendAttempt = async (attempt:Attempt, clearDraft:boolean) => {
    const current = drafts.get(installed.id)!;
    if (current.busy || opening) return;
    const body = JSON.parse(attempt.body);
    const attempts = current.attempts.some(item => item.token === attempt.token) ? current.attempts : [...current.attempts, attempt];
    const remaining = attempts.filter(item => item.token !== attempt.token);
    update({busy:true, attempts, experimentId:undefined});
    try {
      const {data} = await api.post(`${toolsBase}/experiments`, {...body, token:attempt.token});
      if (data.status === 'succeeded') {
        update({...(clearDraft ? freshDraft(type) : {}), attempts:remaining, experimentId:data.result.experiment_id, message:{severity:'success', text:`Registered. ExperimentID: ${data.result.experiment_id}. UserDefinedID: ${data.result.user_defined_id ?? body.user_defined_id}.${data.result.reused_existing ? ' Existing note retained.' : ''}${data.warning ? ` ${data.warning}` : ''}`}});
      } else {
        update({message:{severity:data.status === 'unknown' ? 'warning' : 'error', text:data.message},
          ...(data.status === 'error' ? {attempts:remaining} : {})});
      }
    } catch (error: any) {
      const refused = error.response && error.response.status < 500;
      update({message:{severity:refused ? 'error' : 'warning', text:refused ? requestMessage(error) : `Outcome unknown. ${unknownMessage(attempt)}`},
        ...(refused ? {attempts:remaining} : {}), stale:stale || error.response?.status === 404 || (error.response?.status === 409 && requestMessage(error).includes('Experiment type changed'))});
    } finally { update({busy:false}); }
  };

  const fields = (group?:string) => <Box sx={{display:'grid', gridTemplateColumns: type.layout ? (wide ? 'repeat(2, minmax(0, 1fr))' : '1fr') : {xs:'1fr', sm:'repeat(2, minmax(0, 1fr))'}, gap:2}}>
    {type.parameters.filter(p => !group || p.group === group).map(field => <TextField key={field.name} label={field.label}
      value={parameters[field.name] ?? ''} onChange={e => setParameters({...parameters,[field.name]:e.target.value})}
      select={!!field.allowed && !field.fixed} type={!field.allowed && ['integer','number'].includes(field.type) ? 'number' : 'text'}
      helperText={field.fixed ? 'Default' : undefined} InputProps={{readOnly:!!field.fixed}}
      inputProps={{min:field.min, max:field.max, step:field.type === 'integer' ? 1 : 'any'}} disabled={busy} size={wide && type.layout ? 'medium' : 'small'} fullWidth>
      {field.allowed?.map(value => <MenuItem key={value} value={String(value)} disabled={(type.layout?.rules ?? []).some(rule => rule.parameter === field.name && !evaluateLayoutRule(rule, String(value), layout, type.layout!.assignments).valid)}>{value}</MenuItem>)}
    </TextField>)}
  </Box>;
  return <Box component="form" noValidate onSubmit={e => { e.preventDefault(); void submit(); }} >
    <Box sx={{display:'grid', gap:`${spacing.gutter}px`, gridTemplateColumns:'minmax(0, 1fr)',
      '@media (min-width:1280px)':type.layout ? {gridTemplateColumns:'minmax(0, 7fr) minmax(0, 5fr)', gridTemplateRows:'1fr 1fr auto', minHeight:'calc(100vh - 170px)'} : {}}}>
      <Panel fill title="Experiment" sx={{'@media (min-width:1280px)':{gridColumn:type.layout ? 2 : 1}}} bodySx={{display:'flex'}}>
        <Stack spacing={2} sx={{width:'100%', justifyContent:'space-between'}}>
          <Box sx={{display:'grid', gap:2, gridTemplateColumns:type.layout ? '1fr' : {xs:'1fr', sm:'repeat(2, minmax(0, 1fr))'}, flex:1, alignContent:'space-between'}}>
            {picker ? cloneElement(picker as React.ReactElement<{disabled:boolean}>, {disabled:busy || opening}) : <Typography color="text.secondary">{type.name}</Typography>}
            <TextField label="UserDefinedID" size={wide && type.layout ? 'medium' : 'small'} value={userDefinedId} onChange={e => setUserDefinedId(e.target.value)} disabled={busy} inputProps={{maxLength:255}} fullWidth />
            <TextField sx={{gridColumn:'1 / -1'}} label="Note" size={wide && type.layout ? 'medium' : 'small'} value={note} onChange={e => setNote(e.target.value)} disabled={busy} multiline inputProps={{maxLength:4000}} fullWidth />
            <FormControlLabel sx={{gridColumn:'1 / -1'}} control={<Switch checked={schedule} onChange={e => setSchedule(e.target.checked)} disabled={busy} />} label="Make active in EvoYeast" />
            <Typography sx={{gridColumn:'1 / -1'}} variant="body2" color="text.secondary">Replaces the active experiment. Does not start a run.</Typography>
            {schedule && <Box sx={{gridColumn:'1 / -1'}}>
              {activeError ? <Alert severity="error">Active experiment unavailable: {activeError}</Alert>
                : active === null ? <Typography>Loading active experiment...</Typography>
                : <><Typography>Active experiment: {active.length === 0 ? 'None' : active.map(row => `${row.user_defined_id} (ExperimentID: ${row.experiment_id})`).join(', ')}</Typography>
                  {active.length > 1 && <Alert severity="warning">Multiple active experiments.</Alert>}</>}
            </Box>}
          </Box>

        </Stack>
      </Panel>
          {type.layout && <Panel fill sx={{'@media (min-width:1280px)':{gridColumn:1, gridRow:'1 / 4'}}} bodySx={{display:'flex', flexDirection:'column'}} title="Plate layout" actions={<Typography variant="caption" color="text.secondary">96 wells</Typography>}>
        <ExperimentPlateGrid key={`${type.id}:${type.sha256}`} assignments={type.layout.assignments} value={layout} onChange={setLayout} disabled={busy} />
      </Panel>}
      <Panel fill sx={{'@media (min-width:1280px)':{gridColumn:type.layout ? 2 : 1}}} bodySx={{p:3, display:'flex', flexDirection:'column', justifyContent:'center', '& > .MuiStack-root':{flex:1}, '& .MuiStack-root > .MuiBox-root:first-of-type':{flex:1, alignContent:'space-between'}}} title="Parameters"><Stack spacing={2}>
        {fields(showAllParameters ? undefined : 'main')}
        {!showAllParameters && type.parameters.some(p => p.group === 'more') && <Box component="details" key={type.id}>
          <Typography component="summary" sx={{cursor:'pointer', color:'text.secondary', py:1}}>More parameters</Typography>
          <Box sx={{pt:2}}>{fields('more')}</Box>
        </Box>}
      </Stack></Panel>
      <Box sx={{display:'flex', flexDirection:'column', gap:1.5, p:2, border:1, borderColor:'divider', borderRadius:`${spacing.radius}px`, bgcolor:'background.paper'}}>
        {summary && <Typography aria-label="Layout summary">{summary}{!ruleFailure && ruleResults.length ? `; each round keeps ${ruleResults.map(result => result.kept).join(', ')}` : ''}</Typography>}
        {ruleFailure && <Typography role="status" color="error.main">{ruleFailure}</Typography>}
        {loadError ? <Alert severity="error" action={<Button color="inherit" onClick={reload} disabled={busy}>Reload types</Button>}>{loadError}</Alert> : stale && <Alert severity="warning">{removed ? 'Experiment type is no longer installed.' : 'Experiment type changed. Reload types to start from its defaults.'}
          <Button onClick={reload} disabled={busy}>Reload types</Button>
        </Alert>}
        {message && <Alert severity={message.severity}>{message.text}</Alert>}
        {handoffError && <Alert severity="error" action={<Button component={Link} to="/database?section=settings" color="inherit">Database settings</Button>}>{handoffError}</Alert>}
        <Stack direction="row" gap={1} justifyContent="flex-end" flexWrap="wrap">
          {draft.attempts.map((attempt,index) => <Button key={attempt.token} disabled={busy || opening} onClick={() => void sendAttempt(attempt, false)}>Recover receipt {index + 1}</Button>)}
          {draft.experimentId != null && <Button disabled={busy || opening} onClick={() => void openScheduling()}>Open Scheduling</Button>}
          <Button type="submit" variant="contained" disabled={busy || opening || stale || !!loadError || !!ruleFailure}>Register</Button>
        </Stack>
      </Box>
    </Box>
  </Box>;
}
