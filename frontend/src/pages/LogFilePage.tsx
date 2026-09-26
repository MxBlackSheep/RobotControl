import React, {useEffect,useState} from 'react';
import {Alert,Button,LinearProgress} from '@mui/material';
import {useSearchParams} from 'react-router-dom';
import {PageContent,PageHeader} from '../components/PageLayout';
import {useModuleSection} from '../components/navigation';
import SectionPanel from '../components/SectionPanel';
import {useAuth} from '../context/AuthContext';
import {logFileApi,LogFileSource} from '../services/logFileApi';
import LogSourceBrowser from '../components/LogSourceBrowser';
const sourceIds=['python_log','hamilton_logfiles','robotcontrol_logs'];
export default function LogFilePage(){
 const {user}=useAuth();const [section,setSection]=useModuleSection('/logfile',user);const [params]=useSearchParams();
 const [sources,setSources]=useState<LogFileSource[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true),[refresh,setRefresh]=useState(0);
 useEffect(()=>{let current=true;setLoading(true);logFileApi.getSources().then(data=>{if(!current)return;setSources(data);setError('');
   if(!params.get('section')){const first=sourceIds.findIndex(id=>data.some(s=>s.id===id&&s.exists&&s.accessible&&s.permissions?.can_access!==false));if(first>0)setSection(first);}
 }).catch(()=>{if(current)setError('Unable to load log sources. Retry to check availability.');}).finally(()=>{if(current)setLoading(false);});return()=>{current=false;};},[refresh]);
 return <PageContent><PageHeader title="Logs"/>{loading&&<LinearProgress/>}{error&&<Alert severity="error" action={<Button onClick={()=>setRefresh(v=>v+1)}>Retry</Button>}>{error}</Alert>}
   {sourceIds.map((id,index)=>{const source=sources.find(s=>s.id===id);return <SectionPanel key={id} active={section===index}>{source&&source.exists&&source.accessible&&source.permissions?.can_access!==false?<LogSourceBrowser source={source} active={section===index}/>:!loading&&<Alert severity="warning" action={<Button onClick={()=>setRefresh(v=>v+1)}>Retry</Button>}>{source?.label||id} is unavailable. {source?.error || (source?.permissions?.can_access===false?'This source requires an administrator or a local session.':'The configured folder is missing or inaccessible.')}</Alert>}</SectionPanel>;})}
 </PageContent>;
}
