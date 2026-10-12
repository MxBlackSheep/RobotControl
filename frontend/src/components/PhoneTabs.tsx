import Box from '@mui/material/Box';
import ButtonBase from '@mui/material/ButtonBase';
import { Dashboard, MoreHoriz, Schedule, Videocam } from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { phoneTabFor, visiblePhoneTabs } from './navigation';

// The desktop rail's icons for the same places; More has no rail equivalent.
const icons = { now: Dashboard, runs: Schedule, camera: Videocam, more: MoreHoriz };

/** Phone navigation (below 900px): four fixed tabs, the last row of the app frame. */
export default function PhoneTabs() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const attention = robotAttention(useRobotStatusContext().status);
  const current = phoneTabFor(pathname);
  return <Box component="nav" aria-label="Pages" sx={{
    flexShrink: 0, zIndex: theme => theme.zIndex.appBar, display: 'flex', px: 0.5, pt: 0.5,
    bgcolor: 'background.paper', borderTop: 1, borderColor: 'divider', pb: 'max(4px, env(safe-area-inset-bottom))',
  }}>
    {visiblePhoneTabs(user).map(tab => {
      const Icon = icons[tab.id];
      const selected = tab.id === current;
      const badge = tab.id === 'now' && attention;
      return <ButtonBase key={tab.id} component={Link} to={tab.to} aria-current={selected ? 'page' : undefined}
        aria-label={badge ? `${tab.label}, ${attention.label}` : undefined}
        sx={{ flex: 1, minWidth: 0, minHeight: 48, flexDirection: 'column', gap: '2px', borderRadius: 2, fontSize: 11, fontWeight: 600,
          color: selected ? 'primary.main' : 'text.secondary' }}>
        <Box component="span" sx={{ position: 'relative', display: 'flex' }}>
          <Icon aria-hidden sx={{ fontSize: 24 }} />
          {badge && <Box component="span" aria-hidden sx={{ position: 'absolute', top: -1, right: -5, width: 9, height: 9, borderRadius: 5,
            bgcolor: 'attentionSurface.action', boxShadow: theme => `0 0 0 2px ${theme.palette.background.paper}` }} />}
        </Box>
        {tab.label}
      </ButtonBase>;
    })}
  </Box>;
}
