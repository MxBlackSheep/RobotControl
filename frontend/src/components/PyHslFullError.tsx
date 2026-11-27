import { Box, Typography } from '@mui/material';
import { fontMono } from '../theme';

/** The whole error of a failed scheduled PyHSL run, under its one-line message. RobotControl keeps it, so it stays
 *  readable after PyHSL no longer has the run. */
export default function PyHslFullError({ error }: { error: string | null }) {
  if (!error) return null;
  return <Box sx={{ mt: 1, minWidth: 0, width: '100%' }}>
    <Typography variant="caption" color="text.secondary">Full error</Typography>
    <Box component="pre" tabIndex={0} aria-label="Full error" sx={{ m: 0, maxHeight: 240, overflow: 'auto', fontFamily: fontMono, fontSize: 12, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{error}</Box>
  </Box>;
}
