import { Box, Link, Typography } from '@mui/material';
import { fontMono, layout } from '../../theme';
import { dayTime } from '../../utils/displayTime';
import { ListRow, Panel } from '../PageLayout';
import type { ExperimentFolder } from './VideoArchiveTab';

/** The newest recording folders beside or below the live image; the archive owns browsing and downloads. */
export default function RecentRecordings({ folders, loading, error, onOpenArchive }: {
  folders: ExperimentFolder[]; loading: boolean; error: string; onOpenArchive: () => void;
}) {
  const recent = [...folders].sort((a, b) => (b.creation_time || '').localeCompare(a.creation_time || '')).slice(0, 4);
  const message = error ? 'Recordings unavailable. Open the video archive to retry.' : !recent.length ? (loading ? 'Loading recordings…' : 'No recordings yet.') : '';
  return <Panel title="Recent recordings" inset={false}
    actions={<Link component="button" type="button" underline="hover" onClick={onOpenArchive} sx={{ fontSize: 13 }}>Video archive</Link>}>
    {message && <Typography variant="body2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', minHeight: layout.row, px: 2 }}>{message}</Typography>}
    {recent.map(folder => <ListRow key={folder.folder_name} columns="minmax(0, 1fr) auto auto">
      <Box component="span" sx={{ fontFamily: fontMono, fontSize: 12 }} title={folder.folder_name}>{folder.folder_name}</Box>
      <Box component="span" sx={{ fontFamily: fontMono, fontSize: 12, color: 'text.secondary' }}>{folder.creation_time ? dayTime(folder.creation_time) : 'Time unknown'}</Box>
      <Box component="span" sx={{ color: 'text.secondary', textAlign: 'right' }}>{folder.video_count} {folder.video_count === 1 ? 'video' : 'videos'}</Box>
    </ListRow>)}
  </Panel>;
}
