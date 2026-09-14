import React, {useEffect, useRef, useState} from 'react';
import {Alert, Box, Button, Checkbox, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, LinearProgress, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TableSortLabel, TextField, Typography} from '@mui/material';
import {databaseAPI} from '../services/api';
import {collectMatchingRows, formatExport} from './databaseExport';
type Filter = {column: string; operator: string; value: string};
type Query = {page: number; limit: number; search: string; filters: Filter[]; order: string; direction: 'asc'|'desc'};
const initialQuery: Query = {page:0,limit:25,search:'',filters:[],order:'',direction:'asc'};
export const queryParams = (query: Query) => ({search:query.search || undefined, order_by:query.order || undefined, sort_direction:query.direction, filters:JSON.stringify(Object.fromEntries(query.filters.filter(f=>f.column && f.value.trim()).map(f=>[f.column,{operator:f.operator,value:f.value}])))});
const errorText = (error:any) => error.response?.data?.error?.details || error.response?.data?.detail || error.message || 'Unable to load table';
export default function DatabaseTable(props:{tableName:string; onError?:(message:string)=>void; active?:boolean}) {
  return <TableView key={props.tableName} {...props} />;
}
function TableView({tableName, active=true}:{tableName:string; active?:boolean}) {
  const [query,setQuery]=useState<Query>(initialQuery), [draft,setDraft]=useState(''), [filterDraft,setFilterDraft]=useState<Filter[]>([]);
  const [data,setData]=useState<{columns:string[];rows:Record<string,any>[];total_count:number}|null>(null);
  const [loading,setLoading]=useState(false), [error,setError]=useState(''), [updated,setUpdated]=useState(''), [refresh,setRefresh]=useState(0);
  const [dialog,setDialog]=useState<'filters'|'columns'|'export'|null>(null), [hidden,setHidden]=useState<string[]>([]), [cell,setCell]=useState<{column:string;value:any}|null>(null);
  const [scope,setScope]=useState('page'), [format,setFormat]=useState<'csv'|'json'>('csv'), [progress,setProgress]=useState<number|null>(null), [exportMessage,setExportMessage]=useState('');
  const exportAbort=useRef<AbortController|null>(null);
  useEffect(()=>()=>exportAbort.current?.abort(),[]);
  useEffect(()=>{
    if (!active) return;
    const abort=new AbortController(); let current=true;
    setLoading(true); setError('');
    databaseAPI.getTableData(tableName,query.page+1,query.limit,queryParams(query),abort.signal).then(response=>{
      if(!current)return; const payload=response.data.data; setData(payload); setUpdated(new Date().toLocaleTimeString());
    }).catch(error=>{if(current && !abort.signal.aborted)setError(String(errorText(error)));}).finally(()=>{if(current)setLoading(false);});
    return ()=>{current=false;abort.abort();};
  },[tableName,query,refresh,active]);
  const apply=()=>setQuery(q=>({...q,page:0,search:draft.trim(),filters:filterDraft.map(f=>({...f}))}));
  const exportData=async()=>{
    if(!data)return; const abort=new AbortController();exportAbort.current=abort;setProgress(0);setExportMessage('');
    try {
      const columns=data.columns.filter(c=>!hidden.includes(c));
      const rows=scope==='page'?data.rows:await collectMatchingRows(async(page,limit)=>{
        const response=await databaseAPI.getTableData(tableName,page,limit,queryParams(query),abort.signal);return response.data.data;
      },abort.signal,setProgress);
      if(abort.signal.aborted)return;
      const text=formatExport(columns,rows,format);const url=URL.createObjectURL(new Blob([text],{type:format==='csv'?'text/csv;charset=utf-8':'application/json'}));
      const link=document.createElement('a');link.href=url;link.download=`${tableName}.${format}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      setExportMessage(`Exported ${rows.length.toLocaleString()} rows.`);
    }catch(error){setExportMessage(abort.signal.aborted?'Export cancelled.':String(errorText(error)));}
    finally{setProgress(null);exportAbort.current=null;}
  };
  const columns=data?.columns.filter(c=>!hidden.includes(c)) || [];
  return <Paper variant="outlined" sx={{minWidth:0,overflow:'hidden'}}>
    <Stack spacing={1} sx={{p:1.5}}>
      <Typography variant="h6" sx={{overflowWrap:'anywhere'}}>{tableName}</Typography>
      <Box component="form" onSubmit={event=>{event.preventDefault();apply();}} sx={{display:'flex',gap:1,flexWrap:'wrap'}}>
        <TextField size="small" label="Search all supported columns" value={draft} onChange={e=>setDraft(e.target.value)} inputProps={{maxLength:200}} sx={{flex:'1 1 240px'}} />
        <Button type="submit" variant="contained">Apply</Button>
        <Button onClick={()=>{setDraft('');setFilterDraft([]);setQuery(q=>({...q,page:0,search:'',filters:[]}));}}>Clear</Button>
        <Button onClick={()=>setDialog('filters')}>Filters ({query.filters.filter(f=>f.value).length})</Button>
        <Button onClick={()=>setDialog('columns')} disabled={!data}>Columns</Button>
        <Button onClick={()=>setRefresh(v=>v+1)} disabled={loading}>Refresh</Button>
        <Button onClick={()=>{setExportMessage('');setDialog('export');}} disabled={!data || loading || !!error}>Export</Button>
      </Box>
      <Typography variant="caption" color="text.secondary">{data ? `${data.total_count.toLocaleString()} matching rows`:'Select search and filters, then Apply.'}{updated && ` · Updated ${updated}`}. Search applies to text, numeric and date columns; binary and complex columns are excluded.</Typography>
      {error && <Alert severity="error">{error}{data && ' Previous rows are shown; refresh to retry.'}</Alert>}
    </Stack>
    {loading && <LinearProgress aria-label="Loading table" />}
    <TableContainer sx={{maxHeight:'min(65vh, 720px)',minHeight:160}} tabIndex={0} aria-label={`${tableName} rows`}>
      <Table size="small" stickyHeader><TableHead><TableRow>{columns.map(column=><TableCell key={column} sortDirection={query.order===column?query.direction:false}><TableSortLabel active={query.order===column} direction={query.order===column?query.direction:'asc'} onClick={()=>setQuery(q=>({...q,page:0,order:column,direction:q.order===column && q.direction==='asc'?'desc':'asc'}))}>{column}</TableSortLabel></TableCell>)}</TableRow></TableHead>
        <TableBody>{data?.rows.map((row,index)=><TableRow key={index} hover>{columns.map(column=><TableCell key={column}><Box component="button" onClick={()=>setCell({column,value:row[column]})} aria-label={`View ${column}, row ${index+1}`} sx={{display:'block',border:0,bgcolor:'transparent',color:row[column]==null?'text.secondary':'inherit',textAlign:'left',font:'inherit',cursor:'pointer',minHeight:32,maxWidth:260,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{row[column]==null?'NULL':row[column]===''?'(empty string)':String(row[column])}</Box></TableCell>)}</TableRow>)}
        {!loading && !data?.rows.length && <TableRow><TableCell colSpan={Math.max(columns.length,1)}>{error?'Table unavailable.':query.search || query.filters.length?'No rows match the applied search and filters.':'This table is empty.'}</TableCell></TableRow>}</TableBody>
      </Table>
    </TableContainer>
    <TablePagination component="div" count={data?.total_count||0} page={query.page} rowsPerPage={query.limit} rowsPerPageOptions={[25,50,100]} onPageChange={(_,page)=>setQuery(q=>({...q,page}))} onRowsPerPageChange={e=>setQuery(q=>({...q,page:0,limit:Number(e.target.value)}))} sx={{'& .MuiTablePagination-toolbar':{flexWrap:'wrap',px:1}}} />
    <Dialog open={!!cell} onClose={()=>setCell(null)} fullWidth maxWidth="md"><DialogTitle>{cell?.column}</DialogTitle><DialogContent dividers><Box component="pre" sx={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',m:0}}>{cell?.value==null?'NULL':cell.value===''?'(empty string)':String(cell.value)}</Box></DialogContent><DialogActions><Button autoFocus onClick={()=>setCell(null)}>Close</Button></DialogActions></Dialog>
    <Dialog open={dialog==='columns'} onClose={()=>setDialog(null)} fullWidth maxWidth="xs"><DialogTitle>Visible columns</DialogTitle><DialogContent dividers>{data?.columns.map(column=><FormControlLabel key={column} sx={{display:'flex'}} label={column} control={<Checkbox checked={!hidden.includes(column)} disabled={columns.length===1 && !hidden.includes(column)} onChange={(_,checked)=>setHidden(h=>checked?h.filter(c=>c!==column):[...h,column])} />} />)}</DialogContent><DialogActions><Button onClick={()=>setDialog(null)}>Done</Button></DialogActions></Dialog>
    <Dialog open={dialog==='filters'} onClose={()=>setDialog(null)} fullWidth maxWidth="sm"><DialogTitle>Column filters</DialogTitle><DialogContent dividers><Stack spacing={2}>
      <Typography variant="body2">All conditions must match. Changes apply only when you choose Apply filters.</Typography>
      {filterDraft.map((filter,index)=><Stack key={index} spacing={1}>
        <TextField select size="small" label="Column" value={filter.column} onChange={e=>setFilterDraft(f=>f.map((v,i)=>i===index?{...v,column:e.target.value}:v))}>{data?.columns.map(c=><MenuItem key={c} value={c} disabled={filterDraft.some((f,i)=>i!==index && f.column===c)}>{c}</MenuItem>)}</TextField>
        <TextField select size="small" label="Condition" value={filter.operator} onChange={e=>setFilterDraft(f=>f.map((v,i)=>i===index?{...v,operator:e.target.value}:v))}>{['contains','equals','starts_with','ends_with'].map(op=><MenuItem key={op} value={op}>{op.replace(/_/g,' ')}</MenuItem>)}</TextField>
        <TextField size="small" label="Value" value={filter.value} onChange={e=>setFilterDraft(f=>f.map((v,i)=>i===index?{...v,value:e.target.value}:v))} /><Button onClick={()=>setFilterDraft(f=>f.filter((_,i)=>i!==index))}>Remove condition</Button>
      </Stack>)}<Button onClick={()=>setFilterDraft(f=>[...f,{column:'',operator:'contains',value:''}])}>Add condition</Button>
    </Stack></DialogContent><DialogActions><Button onClick={()=>setDialog(null)}>Keep draft</Button><Button variant="contained" onClick={()=>{apply();setDialog(null);}}>Apply filters</Button></DialogActions></Dialog>
    <Dialog open={dialog==='export'} onClose={()=>{if(progress===null)setDialog(null);}} fullWidth maxWidth="sm"><DialogTitle>Export table data</DialogTitle><DialogContent dividers><Stack spacing={2}>
      <TextField select label="Rows" value={scope} disabled={progress!==null} onChange={e=>setScope(e.target.value)}><MenuItem value="page">Current page</MenuItem><MenuItem value="all">All matching rows</MenuItem></TextField>
      <TextField select label="Format" value={format} disabled={progress!==null} onChange={e=>setFormat(e.target.value as 'csv'|'json')}><MenuItem value="csv">CSV</MenuItem><MenuItem value="json">JSON</MenuItem></TextField>
      <Alert severity="info">Uses the applied search, filters, sort and visible columns. Concurrent database writes may change rows during export; this is not a database snapshot. Exports exceeding 50 MB must be narrowed with filters.</Alert>
      {progress!==null && <><LinearProgress /><Typography>{progress.toLocaleString()} rows collected</Typography></>}{exportMessage && <Alert severity="info">{exportMessage}</Alert>}
    </Stack></DialogContent><DialogActions>{progress!==null?<Button onClick={()=>exportAbort.current?.abort()}>Cancel export</Button>:<><Button onClick={()=>setDialog(null)}>Close</Button><Button variant="contained" onClick={exportData}>Download</Button></>}</DialogActions></Dialog>
  </Paper>;
}
