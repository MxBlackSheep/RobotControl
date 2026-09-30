import { useEffect, useState } from 'react';
import { Box, Button, Link as MuiLink } from '@mui/material';
import WarningAmber from '@mui/icons-material/WarningAmber';
import { Link } from 'react-router-dom';
import { robotAttention, ROBOT_STATUS_INTERVAL_MS, useRobotStatusContext } from '../hooks/useRobotStatus';

function age(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return seconds < 60 ? `${seconds} s` : `${Math.round(seconds / 60)} min`;
}

/**
 * Shown on every page only when an operator is needed or the robot status cannot be trusted.
 * Normal operation has no bar; Overview shows the full state. A failed read never looks like
 * "all clear", and the last known hold stays visible while reads fail.
 */
export default function RobotAttentionBanner() {
  const { status, error, pending, refresh } = useRobotStatusContext();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  const attention = robotAttention(status);
  const stale = !!status && (!!error || now - status.receivedAt > ROBOT_STATUS_INTERVAL_MS * 2 + 5000);
  const unavailable = !status && !!error;
  if (!attention && !stale && !unavailable) return null;

  return <Box role="region" aria-label="Robot status" sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', columnGap: 2, rowGap: 0.5, minHeight: 44, px: { xs: 2, sm: 3 }, py: 0.5,
    fontSize: 14, bgcolor: theme => theme.palette.tone.attention.bg, color: theme => theme.palette.tone.attention.fg, borderBottom: 1, borderColor: 'divider' }}>
    {attention && <MuiLink component={Link} to="/scheduling?section=recovery" underline="hover" color="inherit" aria-label={attention.label}
      sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600, minHeight: 36 }}>
      <WarningAmber fontSize="small" />{attention.label}
    </MuiLink>}
    <Box sx={{ flex: 1 }} />
    {(stale || unavailable) && <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <span>{unavailable ? (pending ? 'Robot status unavailable · retrying…' : 'Robot status unavailable') : `Robot status updated ${age(now - status!.receivedAt)} ago`}</span>
      <Button size="small" color="inherit" onClick={refresh} disabled={pending}>Retry</Button>
    </Box>}
  </Box>;
}
