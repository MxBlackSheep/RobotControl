import { cloneElement, useEffect, useState, useSyncExternalStore } from 'react';
import { Alert, Box, Button, FormControlLabel, MenuItem, Stack, Switch, TextField, Typography, useMediaQuery } from '@mui/material';
import { Link } from 'react-router-dom';
import { Panel } from '../PageLayout';
import { layout as spacing } from '../../theme';
import { api } from '../../services/api';
import { requestMessage, toolsBase } from '../ReportInputs';
import ExperimentPlateGrid, { PlateAssignment, PlateLayout, wells } from './ExperimentPlateGrid';

import { evaluateLayoutRule, LayoutRule } from './experimentLayoutRules';

type Parameter = {name:string; label:string; type:'number'|'integer'|'text'|'choice'; default:string|number;
  min?:number; max?:number; allowed?:(string|number)[]; group:'main'|'more'; fixed?:boolean};
type ExperimentType = {id:string; name:string; package_id:string; package_version:string; sha256:string; parameters:Parameter[];
  layout?:{kind:'plate96'; assignments:PlateAssignment[]; default:[string,string][]; required:string[]; rules?:LayoutRule[]}};
const defaults = (type:ExperimentType) => Object.fromEntries(type.parameters.map(p => [p.name, String(p.default)]));
const defaultLayout = (type:ExperimentType):PlateLayout => Object.fromEntries(type.layout?.default ?? []);
type Message = {severity:'error'|'warning'|'success'; text:string} | null;
type Draft = {definition:ExperimentType; userDefinedId:string; note:string; schedule:boolean; parameters:Record<string,string>; layout:PlateLayout;
  message:Message; attempt:{body:string; token:string; warnedBody?:string} | null; busy:boolean; stale:boolean};
const freshDraft = (definition:ExperimentType):Draft => ({definition, userDefinedId:'', note:'', schedule:false,
  parameters:defaults(definition), layout:defaultLayout(definition), message:null, attempt:null, busy:false, stale:false});
// Session drafts include the reviewed definition and unresolved token, and survive section navigation.
const drafts = new Map<string,Draft>();
const listeners = new Set<() => void>();
const subscribe = (listener:() => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; };
let selectedType = '';
export default function ExperimentForm() {
  const [types, setTypes] = useState<ExperimentType[] | null>(null);
  const [loadError, setLoadError] = useState('');
  const [typeId, setTypeId] = useState(selectedType);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoadError('');
    api.get<ExperimentType[]>(`${toolsBase}/experiments/types`, {signal:controller.signal}).then(({data}) => {
      if (controller.signal.aborted) return;
      setTypes(data);
      for (const definition of data) {
        const draft = drafts.get(definition.id);
        if (draft?.stale && draft.definition.sha256 === definition.sha256 && draft.definition.package_version === definition.package_version) {
          drafts.set(definition.id, {...draft, stale:false});
          listeners.forEach(listener => listener());
        }
      }
      if (!selectedType && data.length === 1) { selectedType = data[0].id; setTypeId(selectedType); }
    }).catch(error => { if (!controller.signal.aborted) setLoadError(requestMessage(error)); });
    return () => controller.abort();
  }, [revision]);
  const chooseType = (id:string) => { selectedType = id; setTypeId(id); };
  const reload = () => setRevision(value => value + 1);
  const type = types?.find(t => t.id === typeId);
  const picker = types && types.length > 1 ? <TextField select label="Experiment type" value={type ? typeId : ''}
    onChange={e => chooseType(e.target.value)} fullWidth disabled={drafts.get(typeId)?.busy}>
    {types.map(t => <MenuItem key={t.id} value={t.id}>{t.name}</MenuItem>)}
  </TextField> : null;
  if (loadError) return <Alert severity="error" action={<Button color="inherit" onClick={reload}>Reload types</Button>}>{loadError}</Alert>;
  if (!types) return <Panel title="Experiments"><Typography color="text.secondary">Loading experiment types...</Typography></Panel>;
  if (!type) return <Panel title="Experiments"><Stack spacing={2} alignItems="flex-start">
    {typeId && <Alert severity="error">Experiment type is no longer installed. Its draft is kept.</Alert>}
    {types.length ? <>{picker ?? <Button onClick={() => chooseType(types[0].id)}>{types[0].name}</Button>}<Typography color="text.secondary">Choose an experiment type.</Typography></> : <>
      <Typography color="text.secondary">No experiment types installed.</Typography>
      <Button component={Link} to="/database?section=packages" variant="outlined">Manage packages</Button>
    </>}
    <Button onClick={reload}>Reload types</Button>
  </Stack></Panel>;
  return <ExperimentDraft key={type.id} installed={type} picker={picker} reload={reload} />;
}
function ExperimentDraft({installed, picker, reload}:{installed:ExperimentType; picker:React.ReactNode; reload:()=>void}) {
  if (!drafts.has(installed.id)) drafts.set(installed.id, freshDraft(installed));
  const draft = useSyncExternalStore(subscribe, () => drafts.get(installed.id)!);
  const update = (patch:Partial<Draft>) => {
    drafts.set(installed.id, {...drafts.get(installed.id)!, ...patch});
    listeners.forEach(listener => listener());
  };
  const {definition:type, userDefinedId, note, schedule, parameters, layout, message, busy} = draft;
  const stale = draft.stale || type.sha256 !== installed.sha256 || type.package_version !== installed.package_version;
  const setUserDefinedId = (userDefinedId:string) => update({userDefinedId});
  const setNote = (note:string) => update({note});
  const setSchedule = (schedule:boolean) => update({schedule});
  const setParameters = (parameters:Record<string,string>) => update({parameters});
  const setLayout = (layout:PlateLayout) => update({layout});
  const setMessage = (message:Message) => update({message});
  const wide = useMediaQuery('(min-width:1280px)');
  const showAllParameters = wide && type.parameters.length <= 12;
  const useLatest = () => {
    update({definition:installed, stale:false,
      parameters:Object.fromEntries(installed.parameters.map(p => [p.name, p.fixed ? String(p.default) : parameters[p.name] ?? String(p.default)])),
      layout:installed.layout ? Object.fromEntries(Object.entries(layout).filter(([,value]) => installed.layout!.assignments.some(a => a.value === value))) : {},
      message:{severity:'warning', text:'Review the updated fields before registering.'}});
  };
  const ruleResults = (type?.layout?.rules ?? []).map(rule => evaluateLayoutRule(rule, parameters[rule.parameter] ?? '', layout, type!.layout!.assignments));
  const ruleFailure = ruleResults.find(result => !result.valid)?.reason;
  const summary = type?.layout?.assignments.map(a => {
    const count = Object.values(layout).filter(value => value === a.value).length;
    return `${count} ${a.label.toLowerCase()}${count === 1 ? '' : 's'}`;
  }).join(', ');
  const submit = async () => {
    if (drafts.get(installed.id)!.busy || stale || ruleFailure) return;
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
    const previous = drafts.get(installed.id)!.attempt;
    if (previous && previous.body !== serialized && previous.warnedBody !== serialized) {
      update({attempt:{...previous, warnedBody:serialized}, message:{severity:'warning', text:`Previous outcome unknown. Check UserDefinedID ${JSON.parse(previous.body).user_defined_id} in the database before registering this changed draft.`}});
      return;
    }
    const attempt = previous?.body === serialized ? previous : {body:serialized, token:crypto.randomUUID().replace(/-/g,'')};
    update({busy:true, attempt});
    try {
      const {data} = await api.post(`${toolsBase}/experiments`, {...body, token:attempt.token});
      if (data.status === 'succeeded') {
        update({...freshDraft(type), message:{severity:'success', text:`Registered. ExperimentID: ${data.result.experiment_id}. UserDefinedID: ${data.result.user_defined_id ?? body.user_defined_id}.${data.result.reused_existing ? ' Existing note retained.' : ''}${data.warning ? ` ${data.warning}` : ''}`}});
      } else {
        update({message:{severity:data.status === 'unknown' ? 'warning' : 'error', text:data.message},
          ...(data.status === 'error' ? {attempt:null} : {})});
      }
    } catch (error: any) {
      const refused = error.response && error.response.status < 500;
      update({message:{severity:refused ? 'error' : 'warning', text:refused ? requestMessage(error) : `Outcome unknown. Check UserDefinedID ${body.user_defined_id} and its parameter and plate rows before trying again.`},
        ...(refused ? {attempt:null} : {}), stale:error.response?.status === 404 || (error.response?.status === 409 && requestMessage(error).includes('Experiment type changed'))});
    } finally { update({busy:false}); }
  };

  const fields = (group?:string) => <Box sx={{display:'grid', gridTemplateColumns: type?.layout ? (wide ? 'repeat(2, minmax(0, 1fr))' : '1fr') : {xs:'1fr', sm:'repeat(2, minmax(0, 1fr))'}, gap:2}}>
    {type!.parameters.filter(p => !group || p.group === group).map(field => <TextField key={field.name} label={field.label}
      value={parameters[field.name] ?? ''} onChange={e => setParameters({...parameters,[field.name]:e.target.value})}
      select={!!field.allowed && !field.fixed} type={!field.allowed && ['integer','number'].includes(field.type) ? 'number' : 'text'}
      helperText={field.fixed ? 'Default' : undefined} InputProps={{readOnly:!!field.fixed}}
      inputProps={{min:field.min, max:field.max, step:field.type === 'integer' ? 1 : 'any'}} disabled={busy} size={wide && type?.layout ? 'medium' : 'small'} fullWidth>
      {field.allowed?.map(value => <MenuItem key={value} value={String(value)} disabled={(type?.layout?.rules ?? []).some(rule => rule.parameter === field.name && !evaluateLayoutRule(rule, String(value), layout, type!.layout!.assignments).valid)}>{value}</MenuItem>)}
    </TextField>)}
  </Box>;
  return <Box component="form" noValidate onSubmit={e => { e.preventDefault(); void submit(); }} >
    <Box sx={{display:'grid', gap:`${spacing.gutter}px`, gridTemplateColumns:'minmax(0, 1fr)',
      '@media (min-width:1280px)':type.layout ? {gridTemplateColumns:'minmax(0, 7fr) minmax(0, 5fr)', gridTemplateRows:'1fr 1fr auto', minHeight:'calc(100vh - 170px)'} : {}}}>
      <Panel fill title="Experiment" sx={{'@media (min-width:1280px)':{gridColumn:type.layout ? 2 : 1}}} bodySx={{display:'flex'}}>
        <Stack spacing={2} sx={{width:'100%', justifyContent:'space-between'}}>
          <Box sx={{display:'grid', gap:2, gridTemplateColumns:type.layout ? '1fr' : {xs:'1fr', sm:'repeat(2, minmax(0, 1fr))'}, flex:1, alignContent:'space-between'}}>
            {picker ? cloneElement(picker as React.ReactElement<{disabled:boolean}>, {disabled:busy}) : <Typography color="text.secondary">{type.name}</Typography>}
            <TextField label="UserDefinedID" size={wide && type?.layout ? 'medium' : 'small'} value={userDefinedId} onChange={e => setUserDefinedId(e.target.value)} disabled={busy} inputProps={{maxLength:255}} fullWidth />
            <TextField sx={{gridColumn:'1 / -1'}} label="Note" size={wide && type?.layout ? 'medium' : 'small'} value={note} onChange={e => setNote(e.target.value)} disabled={busy} multiline inputProps={{maxLength:4000}} fullWidth />
            <FormControlLabel sx={{gridColumn:'1 / -1'}} control={<Switch checked={schedule} onChange={e => setSchedule(e.target.checked)} disabled={busy} />} label="Make active in EvoYeast" />
            <Typography sx={{gridColumn:'1 / -1'}} variant="body2" color="text.secondary">Replaces the active experiment. Does not start a run.</Typography>
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
        {stale && <Alert severity="warning">Experiment type changed. Reload types, then review the updated fields.
          <Button onClick={reload} disabled={busy}>Reload types</Button>
          {(type.sha256 !== installed.sha256 || type.package_version !== installed.package_version) && <Button onClick={useLatest} disabled={busy}>Use updated definition</Button>}
        </Alert>}
        {message && <Alert severity={message.severity}>{message.text}</Alert>}
        <Stack direction="row" gap={1} justifyContent="flex-end">
          <Button type="submit" variant="contained" disabled={busy || stale || !!ruleFailure}>Register</Button>
        </Stack>
      </Box>
    </Box>
  </Box>;
}
