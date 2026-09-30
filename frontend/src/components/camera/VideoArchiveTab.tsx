import { DetailTitle, EmptyPanel, Panel } from '../PageLayout';
import { dayTime } from '../../utils/displayTime';
import { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, CircularProgress, LinearProgress, List, ListItemButton, Stack, TablePagination, TextField, Typography } from '@mui/material';
import { Download, FolderOutlined, Refresh } from '@mui/icons-material';
import InspectionWorkspace from '../InspectionWorkspace';
import { fontMono } from '../../theme';

export interface VideoFile { filename: string; timestamp: string; size_bytes: number; duration?: number; }
export interface ExperimentFolder { folder_name: string; video_count: number; total_size_bytes: number; creation_time: string; videos?: VideoFile[]; }
export interface VideoArchiveTabProps {
  experimentFolders: ExperimentFolder[]; loading: boolean; error: string; onRefresh: () => void;
  onDownloadVideo: (filename: string) => void | Promise<void>; downloadingFilename?: string | null;
  downloadBusy?: boolean; onDeleteVideo?: (filename: string) => void;
  onLoadFolderVideos?: (folderName: string) => Promise<VideoFile[]>;
}
interface FolderState { videos: VideoFile[]; loading: boolean; loaded: boolean; error?: string; }
const fileSize = (bytes: number) => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB`
  : bytes >= 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`;

/** One collection/detail workspace. Pagination bounds DOM size without fixed-height wrapped rows. */
export default function VideoArchiveTab({ experimentFolders, loading, error, onRefresh, onDownloadVideo,
  downloadingFilename, downloadBusy = false, onDeleteVideo, onLoadFolderVideos }: VideoArchiveTabProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [fileQuery, setFileQuery] = useState('');
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [cache, setCache] = useState<Record<string, FolderState>>({});
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    setCache(previous => Object.fromEntries(experimentFolders.map(folder => [folder.folder_name,
      folder.videos ? { videos: folder.videos, loading: false, loaded: true }
        : previous[folder.folder_name] || { videos: [], loading: false, loaded: !onLoadFolderVideos }])));
    if (selected && !experimentFolders.some(folder => folder.folder_name === selected)) {
      setSelected(null); setDetailOpen(false);
    }
  }, [experimentFolders, onLoadFolderVideos, selected]);
  const load = async (folder: ExperimentFolder, force = false) => {
    if (!onLoadFolderVideos || folder.videos || (!force && cache[folder.folder_name]?.loaded) || cache[folder.folder_name]?.loading) return;
    setCache(previous => ({ ...previous, [folder.folder_name]: { videos: [], loading: true, loaded: false } }));
    try {
      const videos = await onLoadFolderVideos(folder.folder_name);
      if (mounted.current) setCache(previous => ({ ...previous, [folder.folder_name]: { videos, loading: false, loaded: true } }));
    } catch (failure) {
      if (mounted.current) setCache(previous => ({ ...previous, [folder.folder_name]: { videos: [], loading: false, loaded: false,
        error: failure instanceof Error ? failure.message : 'Could not load recordings.' } }));
    }
  };
  const choose = (folder: ExperimentFolder) => {
    if (selected !== folder.folder_name) { setPage(0); setFileQuery(''); }
    setSelected(folder.folder_name); setDetailOpen(true); void load(folder);
  };
  const folder = experimentFolders.find(item => item.folder_name === selected);
  const state = selected ? cache[selected] : undefined;
  const refreshArchive = () => {
    onRefresh();
    if (folder) void load(folder, true);
  };
  const videos = (state?.videos || folder?.videos || []).filter(video => video.filename.toLowerCase().includes(fileQuery.toLowerCase()));
  const safePage = Math.min(page, Math.max(0, Math.ceil(videos.length / pageSize) - 1));
  return <Stack spacing={1} sx={{ minWidth: 0 }}>
    {error && <Alert severity="error" action={<Button color="inherit" onClick={refreshArchive}>Retry</Button>}>{error}</Alert>}
    <InspectionWorkspace label="Recording archive" selectorLabel="Folders" detailOpen={detailOpen} onBack={() => setDetailOpen(false)}
      selector={<Panel title={`Folders (${experimentFolders.length})`} label="Folders" fill inset={false} sx={{ height: '100%' }} bodySx={{ display: 'flex', flexDirection: 'column' }}
        actions={<Button size="small" onClick={refreshArchive} disabled={loading} startIcon={<Refresh />}>Refresh</Button>}>
        <Box sx={{ px: 2, py: 1.5, borderBottom: 1, borderColor: 'surface.rowLine' }}>
          <TextField label="Search folders" size="small" fullWidth value={query} onChange={event => setQuery(event.target.value)} />
        </Box>
        {loading && <LinearProgress aria-label="Loading recordings" />}
        <List disablePadding sx={{ overflow: 'auto', minHeight: 0, flex: 1 }}>
          {experimentFolders.filter(item => item.folder_name.toLowerCase().includes(query.toLowerCase())).map(item => <ListItemButton
            key={item.folder_name} aria-label={`Open folder ${item.folder_name}`} aria-current={selected === item.folder_name ? 'true' : undefined}
            selected={selected === item.folder_name} onClick={() => choose(item)} sx={{ gap: 1.5, alignItems: 'center', minHeight: 56, py: 1, px: 2, borderBottom: 1, borderColor: 'surface.rowLine' }}>
            <FolderOutlined fontSize="small" sx={{ color: 'text.secondary' }} />
            <Box sx={{ minWidth: 0 }}><Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '20px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.folder_name}>{item.folder_name}</Typography>
              <Typography variant="caption" color="text.secondary">{item.video_count} recordings · {fileSize(item.total_size_bytes)}</Typography></Box>
          </ListItemButton>)}
          {!loading && !experimentFolders.length && <Typography variant="body2" sx={{ p: 2, color: 'text.secondary' }}>No recordings yet.</Typography>}
        </List>
      </Panel>}>
      {folder ? <Panel title="Folder" fill inset={false} sx={{ height: '100%' }} bodySx={{ display: 'flex', flexDirection: 'column' }}>
        <Stack spacing={1.5} sx={{ p: 2, borderBottom: 1, borderColor: 'surface.rowLine' }}>
          <DetailTitle>{folder.folder_name}</DetailTitle>
          <TextField label="Find recording" size="small" value={fileQuery} onChange={event => { setFileQuery(event.target.value); setPage(0); }} sx={{ maxWidth: { sm: 360 } }} />
        </Stack>
        {state?.loading && <LinearProgress aria-label="Loading folder" />}
        {state?.error && <Alert severity="error" sx={{ mx: 2, mb: 1 }} action={<Button onClick={() => void load(folder)}>Retry</Button>}>{state.error}</Alert>}
        <Box sx={{ overflow: 'auto', minHeight: 0, flex: 1 }}>
          {videos.slice(safePage * pageSize, (safePage + 1) * pageSize).map(video => <Stack key={video.filename} direction="row" gap={1.5} flexWrap="wrap"
            alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1, minHeight: 56, borderBottom: 1, borderColor: 'surface.rowLine' }}>
            <Box sx={{ minWidth: 0, flex: '1 1 240px' }}>
              <Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '20px', overflowWrap: 'anywhere' }}>{video.filename}</Typography>
              <Typography variant="caption" color="text.secondary">{dayTime(video.timestamp)} · {fileSize(video.size_bytes)}{video.duration != null ? ` · ${video.duration} s` : ''}</Typography>
            </Box>
            <Stack direction="row" gap={1}>
              <Button aria-label={`Download ${video.filename}`} onClick={() => void onDownloadVideo(video.filename)}
                disabled={downloadBusy} startIcon={downloadingFilename === video.filename ? <CircularProgress size={18} /> : <Download />}>Download</Button>
              {onDeleteVideo && <Button color="error" aria-label={`Delete ${video.filename}`} disabled={downloadBusy} onClick={() => onDeleteVideo(video.filename)}>Delete</Button>}
            </Stack>
          </Stack>)}
          {!state?.loading && !state?.error && !videos.length && <Typography variant="body2" sx={{ p: 2, color: 'text.secondary' }}>No recordings found.</Typography>}
        </Box>
        <TablePagination component="div" count={videos.length} page={safePage} rowsPerPage={pageSize} rowsPerPageOptions={[25, 50, 100]}
          onPageChange={(_, next) => setPage(next)} onRowsPerPageChange={event => { setPageSize(Number(event.target.value)); setPage(0); }}
          sx={{ flexShrink: 0, borderTop: 1, borderColor: 'surface.headLine', px: 1, '& .MuiTablePagination-toolbar': { flexWrap: 'wrap', px: 0 }, '& .MuiTablePagination-spacer': { display: 'none' } }} />
      </Panel> : <EmptyPanel>Select a recording folder.</EmptyPanel>}
    </InspectionWorkspace>
  </Stack>;
}
