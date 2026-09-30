import React, { useEffect, useState } from 'react';
import { Box, Button, Divider, Link as MuiLink, Typography } from '@mui/material';
import WarningAmber from '@mui/icons-material/WarningAmber';
import { Link } from 'react-router-dom';
import { recoveryCount, ROBOT_STATUS_INTERVAL_MS, useRobotStatusContext } from '../hooks/useRobotStatus';

function Dot({ color }: { color: string }) {
  return <Box component="span" aria-hidden sx={{ width: 8, height: 8, borderRadius: 4, bgcolor: color, flexShrink: 0 }} />;
}

function age(ms: number) {
  const seconds = Math.max(0, Math.round(ms / 1000));
  return seconds < 60 ? `${seconds} s` : `${Math.round(seconds / 60)} min`;
}

/** The robot's state on every page. A failed read says so instead of looking like "all clear". */
export default function RobotStatusBar({ compact = false, leading }: { compact?: boolean; leading?: React.ReactNode }) {
  const { status, error, pending, refresh } = useRobotStatusContext();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 5000); return () => clearInterval(timer); }, []);
  const recoveries = recoveryCount(status);
  const storageDown = status?.recovery?.storage_healthy === false;
  const stale = !!status && (!!error || now - status.receivedAt > ROBOT_STATUS_INTERVAL_MS * 2 + 5000);
  const current = status?.running[0];

  const state = !status
    ? <Typography component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600, fontSize: 14 }}>
        <Dot color={error ? 'warning.main' : 'text.disabled'} />{error ? 'Status unavailable' : 'Checking status…'}
      </Typography>
    : <Typography component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600, fontSize: 14, whiteSpace: 'nowrap' }}>
        <Dot color={status.schedulerRunning ? 'primary.main' : 'text.disabled'} />{status.schedulerRunning ? 'Scheduler running' : 'Scheduler stopped'}
      </Typography>;

  const freshness = !status
    ? error && <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, fontSize: 13, color: 'text.secondary' }}>
        {!compact && <span>{pending ? 'Retrying…' : error}</span>}
        <Button size="small" onClick={refresh} disabled={pending}>Retry</Button>
      </Box>
    : stale
      ? <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, fontSize: 13, color: 'warning.main' }}>
          <Dot color="warning.main" /><span>{compact ? age(now - status.receivedAt) : `Updated ${age(now - status.receivedAt)} ago`}</span>
          <Button size="small" onClick={refresh} disabled={pending}>Retry</Button>
        </Box>
      : <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, fontSize: 13, color: 'text.secondary' }}><Dot color="success.main" />Live</Box>;

  const recovery = recoveries > 0 && <MuiLink component={Link} to="/scheduling?section=recovery" underline="none"
    aria-label={storageDown ? 'Scheduler storage needs attention' : `${recoveries} ${recoveries === 1 ? 'run needs' : 'runs need'} recovery`}
    sx={{ display: 'flex', alignItems: 'center', gap: 1, px: 1.5, minHeight: 32, borderRadius: 1, fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap',
      bgcolor: theme => theme.palette.tone.attention.bg, color: theme => theme.palette.tone.attention.fg }}>
    <WarningAmber fontSize="small" />{compact ? recoveries : storageDown ? 'Scheduler storage needs attention' : `${recoveries} ${recoveries === 1 ? 'run needs' : 'runs need'} recovery`}
  </MuiLink>;

  return <Box role="region" aria-label="Robot status" sx={{ display: 'flex', alignItems: 'center', gap: compact ? 1.5 : 2, minHeight: compact ? 44 : 52, px: compact ? 2 : 3,
    bgcolor: 'background.paper', borderBottom: 1, borderColor: 'divider', minWidth: 0, pl: leading ? 0.5 : undefined }}>
    {leading}
    {state}
    {!compact && status && <>
      <Divider orientation="vertical" flexItem sx={{ my: 1.5 }} />
      <Typography component="span" sx={{ fontSize: 14, color: 'text.secondary', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {current ? <>Now <Box component="strong" sx={{ color: 'text.primary', fontWeight: 500 }}>{current.experiment_name}</Box></> : 'Nothing running'}
        {status.queued > 0 && ` · ${status.queued} waiting`}
      </Typography>
    </>}
    <Box sx={{ flex: 1 }} />
    {recovery}
    {freshness}
  </Box>;
}
