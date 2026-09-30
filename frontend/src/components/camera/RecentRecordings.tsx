import { Box, Card, Link, Stack, Typography } from '@mui/material';
import { fontMono } from '../../theme';
import { dayTime } from '../../utils/displayTime';
import type { ExperimentFolder } from './VideoArchiveTab';

/** The newest recording folders below the live image; the archive owns browsing and downloads. */
export default function RecentRecordings({ folders, loading, error, onOpenArchive }: {
  folders: ExperimentFolder[]; loading: boolean; error: string; onOpenArchive: () => void;
}) {
  const recent = [...folders].sort((a, b) => (b.creation_time || '').localeCompare(a.creation_time || '')).slice(0, 4);
  return <Card component="section" aria-label="Recent recordings" variant="outlined" sx={{ mt: 2, p: 2 }}>
    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
      <Typography component="h2" variant="h6">Recent recordings</Typography>
      <Link component="button" type="button" onClick={onOpenArchive} sx={{ fontSize: 14 }}>Video archive</Link>
    </Stack>
    {error ? <Typography sx={{ fontSize: 14, color: 'text.secondary' }}>Recordings unavailable. Open the video archive to retry.</Typography>
      : !recent.length ? <Typography sx={{ fontSize: 14, color: 'text.secondary' }}>{loading ? 'Loading recordings…' : 'No recordings yet.'}</Typography>
      : <Box sx={{ display: 'grid', gap: 1, gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))' }}>
        {recent.map(folder => <Box key={folder.folder_name} sx={{ p: 1.25, border: 1, borderColor: 'divider', borderRadius: 1.5, minWidth: 0 }}>
          <Typography sx={{ fontFamily: fontMono, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={folder.folder_name}>{folder.folder_name}</Typography>
          <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
            {folder.creation_time ? dayTime(folder.creation_time) : 'Time unknown'} · {folder.video_count} {folder.video_count === 1 ? 'video' : 'videos'}
          </Typography>
        </Box>)}
      </Box>}
  </Card>;
}
