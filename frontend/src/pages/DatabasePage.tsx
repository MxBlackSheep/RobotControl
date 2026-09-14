import React, {useEffect,useRef,useState} from 'react';
import {Alert,Box,Button,FormControlLabel,LinearProgress,List,ListItemButton,ListItemText,Paper,Stack,Switch,TextField,Typography} from '@mui/material';
import {PageContent,PageHeader} from '../components/PageLayout';
import {useModuleSection,isLocalUser} from '../components/navigation';
import SectionPanel from '../components/SectionPanel';
import {useAuth} from '../context/AuthContext';
import {databaseAPI} from '../services/api';
import DatabaseTable from '../components/DatabaseTable';
import StoredProcedures from '../components/StoredProcedures';
import DatabaseRestore from '../components/DatabaseRestore';
import DatabaseOperations from '../components/DatabaseOperations';
type TableInfo={name:string;has_data?:boolean;is_important?:boolean};
export default function DatabasePage(){
  const {user}=useAuth();const [section]=useModuleSection('/database',user);
  const [tables,setTables]=useState<TableInfo[]>([]),[selected,setSelected]=useState(''),[search,setSearch]=useState(''),[important,setImportant]=useState(true),[panel,setPanel]=useState(true),[showTable,setShowTable]=useState(false);
  const [loading,setLoading]=useState(false),[error,setError]=useState('');const request=useRef(0);
  const load=async()=>{const id=++request.current;setLoading(true);setError('');try{const response=await databaseAPI.getTables(false);if(id===request.current)setTables(response.data.data.table_details||[]);}catch{if(id===request.current)setError('Unable to refresh tables. Existing entries are retained.');}finally{if(id===request.current)setLoading(false);}};
  useEffect(()=>{void load();return()=>{request.current++;};},[]);
  const filtered=tables.filter(t=>(!important||t.is_important)&&t.name.toLowerCase().includes(search.toLowerCase()));
  return <PageContent><PageHeader title="Database" />{error&&<Alert severity="error" sx={{mb:1}}>{error}</Alert>}
    <SectionPanel active={section===0}>
      <Box sx={{display:'flex',gap:2,alignItems:'flex-start','@container workspace (max-width: 899px)':{flexDirection:'column'}}}>
        <Paper variant="outlined" sx={{width:300,maxWidth:'100%',flexShrink:0,display:panel?'block':'none','@container workspace (max-width: 899px)':{width:'100%',display:showTable?'none':'block'}}}>
          <Stack spacing={1} sx={{p:1.5}}><Typography variant="h6">Tables</Typography><TextField size="small" label="Find a table" value={search} onChange={e=>setSearch(e.target.value)}/><FormControlLabel control={<Switch checked={important} onChange={(_,checked)=>setImportant(checked)}/>} label="Important tables only"/><Button onClick={load} disabled={loading}>Refresh tables</Button></Stack>
          {loading&&<LinearProgress/>}<List aria-label="Database tables" sx={{maxHeight:'65vh',overflowY:'auto',overflowX:'hidden'}}>{filtered.map(table=><ListItemButton key={table.name} selected={selected===table.name} title={table.name} onClick={()=>{setSelected(table.name);setShowTable(true);}}><ListItemText primary={table.name} primaryTypographyProps={{sx:{overflowWrap:'anywhere'}}} secondary={table.has_data===true?'Has data':table.has_data===false?'Empty':'Availability unknown'}/></ListItemButton>)}{!loading&&!filtered.length&&<Typography sx={{p:2}}>No tables match this view.</Typography>}</List>
        </Paper>
        <Box sx={{flex:1,minWidth:0,width:'100%','@container workspace (max-width: 899px)':{display:showTable?'block':'none'}}}>
          <Button sx={{mb:1,'@container workspace (max-width: 899px)':{display:'none'}}} onClick={()=>setPanel(v=>!v)}>{panel?'Hide table list':'Show table list'}</Button>
          <Button sx={{display:'none',mb:1,'@container workspace (max-width: 899px)':{display:'inline-flex'}}} onClick={()=>setShowTable(false)}>Back to tables</Button>
          {selected?<DatabaseTable tableName={selected} active={section===0}/>:<Alert severity="info">Choose a table to inspect its rows. Browsing does not change database records.</Alert>}
        </Box>
      </Box>
    </SectionPanel>
    <SectionPanel active={section===1}><StoredProcedures onError={setError}/></SectionPanel>
    <SectionPanel active={section===2}>{user?.role==='admin'||isLocalUser(user)?<DatabaseRestore onError={setError}/>:null}</SectionPanel>
    <SectionPanel active={section===3}>{isLocalUser(user)?<DatabaseOperations onError={setError}/>:null}</SectionPanel>
  </PageContent>;
}
