import { useEffect, useState } from 'react';
import { Box, Button, Link as MuiLink } from '@mui/material';
import WarningAmber from '@mui/icons-material/WarningAmber';
import CloudOff from '@mui/icons-material/CloudOff';
import { Link } from 'react-router-dom';
import { robotAttention, ROBOT_STATUS_INTERVAL_MS, useRobotStatusContext } from '../hooks/useRobotStatus';
import { layout } from '../theme';
import { useConnectionState } from '../services/requestError';

function age(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return seconds < 60 ? `${seconds} s` : `${Math.round(seconds / 60)} min`;
}

/**
 * Shown on every page only when an operator is needed, the robot status cannot be trusted or
 * the connection to RobotControl is failing (remote use through a tunnel).
 * Normal operation has no bar; Overview shows the full state. A failed read never looks like
 * "all clear", and the last known hold stays visible while reads fail.
 */
export default function RobotAttentionBanner() {
  const { status, error, pending, refresh } = useRobotStatusContext();
  const connection = useConnectionState();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  const attention = robotAttention(status);
  const stale = !!status && (!!error || now - status.receivedAt > ROBOT_STATUS_INTERVAL_MS * 2 + 5000);
  const unavailable = !status && !!error;
  // Explains why data is stale; the latest request outcome (any screen) clears it.
  const connectionLost = !connection.online ? 'This device is offline' : connection.failing ? 'Connection to RobotControl lost · retrying' : null;
  if (!attention && !stale && !unavailable && !connectionLost) return null;

  return <Box role="region" aria-label="Robot status" sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', columnGap: 2, minHeight: layout.touchRow, px: { xs: `${layout.pagePhone}px`, sm: `${layout.page}px` },
    fontSize: 14, bgcolor: 'attentionSurface.head', color: 'attentionSurface.text', borderBottom: 1, borderColor: 'attentionSurface.line' }}>
    {attention && <MuiLink component={Link} to="/scheduling?section=recovery" underline="hover" color="inherit" aria-label={attention.label}
      sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600, minHeight: 36 }}>
      <WarningAmber fontSize="small" />{attention.label}
    </MuiLink>}
    <Box sx={{ flex: 1 }} />
    {connectionLost && <Box role="status" sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600 }}>
      <CloudOff fontSize="small" />{connectionLost}
    </Box>}
    {(stale || unavailable) && <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <span>{unavailable ? (pending ? 'Robot status unavailable · retrying…' : 'Robot status unavailable') : `Robot status updated ${age(now - status!.receivedAt)} ago`}</span>
      <Button size="small" color="inherit" onClick={refresh} disabled={pending}>Retry</Button>
    </Box>}
  </Box>;
}
