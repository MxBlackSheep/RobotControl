import { useEffect, useState } from 'react';
import { Box, Button, Link as MuiLink } from '@mui/material';
import WarningAmber from '@mui/icons-material/WarningAmber';
import CloudOff from '@mui/icons-material/CloudOff';
import { Link, useLocation } from 'react-router-dom';
import { isLocalUser, useSidebarLayout } from './navigation';
import { useAuth } from '../context/AuthContext';
import { clockTime } from '../utils/displayTime';
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
  // Phones: Now and What happened open with the hold itself, so the strip there carries only
  // connection problems; elsewhere it names the held run. Recovery is workstation work, so a
  // remote session is sent to What happened instead.
  const { mobile } = useSidebarLayout();
  const { pathname } = useLocation();
  const { user } = useAuth();
  const showsHold = mobile && (pathname === '/' || pathname === '/held');
  const attention = showsHold ? null : robotAttention(status);
  const first = status?.recovery?.pending_recoveries?.[0];
  const heldName = first?.experiment_name || status?.recovery?.experiment_name;
  const heldAt = first?.triggered_at ? new Date(first.triggered_at) : null;
  const holdText = attention && (mobile && attention.kind === 'recovery' && heldName
    ? `${heldName} held${heldAt && !Number.isNaN(heldAt.getTime()) ? ` since ${clockTime(heldAt)}` : ''}${attention.count > 1 ? ` · ${attention.count - 1} more` : ''}`
    : attention.label);
  const stale = !!status && (!!error || now - status.receivedAt > ROBOT_STATUS_INTERVAL_MS * 2 + 5000);
  const unavailable = !status && !!error;
  // Explains why data is stale; the latest request outcome (any screen) clears it.
  const connectionLost = !connection.online ? 'This device is offline' : connection.failing ? 'Connection to RobotControl lost · retrying' : null;
  if (!attention && !stale && !unavailable && !connectionLost) return null;

  // Phones: a thin strip (the tabs carry the hold too); the link keeps a 44px touch target.
  return <Box role="region" aria-label="Robot status" sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', columnGap: 2, minHeight: mobile ? 32 : layout.touchRow, px: { xs: `${layout.pagePhone}px`, sm: `${layout.page}px` },
    fontSize: mobile ? 13 : 14, bgcolor: 'attentionSurface.head', color: 'attentionSurface.text', borderBottom: 1, borderColor: 'attentionSurface.line' }}>
    {attention && <MuiLink component={Link} to={isLocalUser(user) ? '/scheduling?section=recovery' : '/held'} underline="hover" color="inherit" aria-label={holdText || undefined}
      // 36px inside the 44px band (border included); the pseudo-element makes the touch target 44px.
      sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600, minHeight: mobile ? 28 : 36, position: 'relative', '&::after': { content: '""', position: 'absolute', inset: mobile ? '-8px 0' : '-4px 0' } }}>
      <WarningAmber fontSize="small" />{holdText}
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
