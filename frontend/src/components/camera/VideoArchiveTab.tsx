import { DetailTitle, EmptyPanel, Panel } from '../PageLayout';
import { dayTime } from '../../utils/displayTime';
import { useEffect, useState } from 'react';
import { Alert, Box, Button, CircularProgress, LinearProgress, List, ListItemButton, Stack, Typography } from '@mui/material';
import InspectionWorkspace from '../InspectionWorkspace';
import { fontMono } from '../../theme';

export interface VideoFile { filename: string; timestamp: string; size_bytes: number; duration?: number; }
export interface ExperimentFolder { folder_name: string; video_count: number; total_size_bytes: number; creation_time: string; videos?: VideoFile[]; }
export interface VideoArchiveTabProps {
  experimentFolders: ExperimentFolder[]; loading: boolean; error: string; onRefresh: () => void;
  onDownloadVideo: (filename: string) => void | Promise<void>; downloadingFilename?: string | null; downloadBusy?: boolean;
}
export const fileSize = (bytes: number) => bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB`
  : bytes >= 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} MB` : `${(bytes / 1024).toFixed(1)} KB`;

/** One collection/detail workspace. The backend keeps about 20 folders of about 15 clips, so every row is listed. */
export default function VideoArchiveTab({ experimentFolders, loading, error, onRefresh, onDownloadVideo,
  downloadingFilename, downloadBusy = false }: VideoArchiveTabProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const folder = experimentFolders.find(item => item.folder_name === selected);
  // A folder removed by a refresh closes its detail.
  useEffect(() => {
    if (selected && !folder) { setSelected(null); setDetailOpen(false); }
  }, [selected, folder]);
  const videos = folder?.videos ?? [];
  return <Stack spacing={1} sx={{ minWidth: 0 }}>
    {error && <Alert severity="error" action={<Button color="inherit" onClick={onRefresh}>Retry</Button>}>{error}</Alert>}
    <InspectionWorkspace label="Recording archive" selectorLabel="Folders" detailOpen={detailOpen} onBack={() => setDetailOpen(false)}
      selector={<Panel title={`Folders (${experimentFolders.length})`} label="Folders" fill inset={false} sx={{ height: '100%' }} bodySx={{ display: 'flex', flexDirection: 'column' }}
        actions={<Button size="small" onClick={onRefresh} disabled={loading}>Refresh</Button>}>
        {loading && <LinearProgress aria-label="Loading recordings" />}
        <List disablePadding sx={{ overflow: 'auto', minHeight: 0, flex: 1 }}>
          {experimentFolders.map(item => <ListItemButton
            key={item.folder_name} aria-label={`Open folder ${item.folder_name}`} aria-current={selected === item.folder_name ? 'true' : undefined}
            selected={selected === item.folder_name} onClick={() => { setSelected(item.folder_name); setDetailOpen(true); }}
            sx={{ gap: 1.5, alignItems: 'center', minHeight: 56, py: 1, px: 2, borderBottom: 1, borderColor: 'surface.rowLine' }}>
            <Box sx={{ minWidth: 0 }}><Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '20px', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={item.folder_name}>{item.folder_name}</Typography>
              <Typography variant="caption" color="text.secondary">{item.video_count} recordings · {fileSize(item.total_size_bytes)}</Typography></Box>
          </ListItemButton>)}
          {!loading && !experimentFolders.length && <Typography variant="body2" sx={{ p: 2, color: 'text.secondary' }}>No recordings yet.</Typography>}
        </List>
      </Panel>}>
      {folder ? <Panel title="Folder" fill inset={false} sx={{ height: '100%' }} bodySx={{ display: 'flex', flexDirection: 'column' }}>
        <Box sx={{ p: 2, borderBottom: 1, borderColor: 'surface.rowLine' }}><DetailTitle>{folder.folder_name}</DetailTitle></Box>
        <Box sx={{ overflow: 'auto', minHeight: 0, flex: 1 }}>
          {videos.map(video => <Stack key={video.filename} direction="row" gap={1.5} flexWrap="wrap"
            alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1, minHeight: 56, borderBottom: 1, borderColor: 'surface.rowLine' }}>
            <Box sx={{ minWidth: 0, flex: '1 1 240px' }}>
              <Typography sx={{ fontFamily: fontMono, fontSize: 12, lineHeight: '20px', overflowWrap: 'anywhere' }}>{video.filename}</Typography>
              <Typography variant="caption" color="text.secondary">{dayTime(video.timestamp)} · {fileSize(video.size_bytes)}{video.duration != null ? ` · ${video.duration} s` : ''}</Typography>
            </Box>
            <Button aria-label={`Download ${video.filename}`} onClick={() => void onDownloadVideo(video.filename)}
              disabled={downloadBusy} startIcon={downloadingFilename === video.filename ? <CircularProgress size={18} /> : undefined}>Download</Button>
          </Stack>)}
          {!videos.length && <Typography variant="body2" sx={{ p: 2, color: 'text.secondary' }}>No recordings found.</Typography>}
        </Box>
      </Panel> : <EmptyPanel>Select a recording folder.</EmptyPanel>}
    </InspectionWorkspace>
  </Stack>;
}
