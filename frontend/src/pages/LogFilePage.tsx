import { useEffect, useState } from 'react';
import { Alert, Button, LinearProgress } from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import { PageContent, PageHeader } from '../components/PageLayout';
import { sectionRegistry, useModuleSection } from '../components/navigation';
import SectionPanel from '../components/SectionPanel';
import { useAuth } from '../context/AuthContext';
import { logFileApi, LogFileSource } from '../services/logFileApi';
import LogSourceBrowser from '../components/LogSourceBrowser';

const sections = sectionRegistry['/logfile'];
const available = (source: LogFileSource | undefined) =>
  !!source && source.exists && source.accessible && source.permissions?.can_access !== false;

export default function LogFilePage() {
  const { user } = useAuth();
  const [section, setSection] = useModuleSection('/logfile', user);
  const [params] = useSearchParams();
  const [sources, setSources] = useState<LogFileSource[]>([]),
    [error, setError] = useState(''),
    [loading, setLoading] = useState(true),
    [refresh, setRefresh] = useState(0);

  useEffect(() => {
    let current = true;
    setLoading(true);
    logFileApi.getSources().then(data => {
      if (!current) return;
      setSources(data);
      setError('');
      // Without a chosen section, open the first source this session can read.
      if (!params.get('section')) {
        const first = sections.find(entry => available(data.find(source => source.id === entry.source)));
        if (first && first.index > 0) setSection(first.index);
      }
    }).catch(() => {
      if (current) setError('Unable to load log sources. Retry to check availability.');
    }).finally(() => {
      if (current) setLoading(false);
    });
    return () => { current = false; };
  }, [refresh]);

  const retry = <Button onClick={() => setRefresh(v => v + 1)}>Retry</Button>;
  return <PageContent variant="inspection">
    <PageHeader title="Logs" />
    {loading && <LinearProgress />}
    {error && <Alert severity="error" action={retry}>{error}</Alert>}
    {sections.map(entry => {
      const source = sources.find(item => item.id === entry.source);
      return <SectionPanel key={entry.id} active={section === entry.index}>
        {source && available(source)
          ? <LogSourceBrowser source={source} active={section === entry.index} />
          : !loading && <Alert severity="warning" action={retry}>
            {source?.label || entry.source} is unavailable. {source?.error || (source?.permissions?.can_access === false
              ? 'This source requires an administrator or a local session.'
              : 'The configured folder is missing or inaccessible.')}
          </Alert>}
      </SectionPanel>;
    })}
  </PageContent>;
}
