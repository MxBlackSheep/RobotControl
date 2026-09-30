import React from 'react';
import { Box, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, Tooltip, Typography } from '@mui/material';
import { ChevronLeft, ChevronRight } from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import { NavigationUser, visibleNavigation } from './navigation';
import { recoveryCount, useRobotStatusContext } from '../hooks/useRobotStatus';
import { fontMono } from '../theme';
import { APP_VERSION } from '../version';

/** Modules only; a module's sections are tabs in its page header. */
export default function AppSidebar({ user, mobile, expanded, open, onClose, onToggle, footer }: {
  user: NavigationUser; mobile: boolean; expanded: boolean; open: boolean; onClose: () => void; onToggle: () => void; footer: React.ReactNode;
}) {
  const location = useLocation();
  const recoveries = recoveryCount(useRobotStatusContext().status);
  const wide = mobile || expanded;
  const width = mobile ? 280 : wide ? 224 : 64;
  return <Drawer variant={mobile ? 'temporary' : 'permanent'} open={mobile ? open : true} onClose={onClose}
    sx={{ width: mobile ? 0 : width, flexShrink: 0, '& .MuiDrawer-paper': { width, boxSizing: 'border-box', border: 0, bgcolor: 'rail.bg', color: 'rail.text' } }}>
    <Box component="nav" aria-label="Main navigation" sx={{ display: 'flex', flexDirection: 'column', height: '100%', py: 1.5, px: wide ? 1.5 : 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: wide ? 'space-between' : 'center', minHeight: 48, pl: wide ? 1.25 : 0, mb: 1.5 }}>
        {wide && <Box><Typography sx={{ fontSize: 16, fontWeight: 600, color: 'rail.activeText' }}>RobotControl</Typography>
          <Typography sx={{ fontFamily: fontMono, fontSize: 12, color: 'rail.muted' }}>v{APP_VERSION}</Typography></Box>}
        <IconButton aria-label={mobile ? 'Close navigation' : wide ? 'Collapse navigation' : 'Expand navigation'} onClick={mobile ? onClose : onToggle} sx={{ color: 'rail.text' }}>
          {wide ? <ChevronLeft /> : <ChevronRight />}
        </IconButton>
      </Box>
      <List disablePadding sx={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 0.5 }}>
        {visibleNavigation(user).map(item => {
          const selected = location.pathname === item.path;
          const badge = item.path === '/scheduling' && recoveries > 0;
          return <Tooltip key={item.path} title={wide ? '' : item.label} placement="right">
            <ListItemButton component={Link} to={item.path} selected={selected} aria-label={badge ? `${item.label}, recovery requires attention` : item.label}
              aria-current={selected ? 'page' : undefined} onClick={() => { if (mobile) onClose(); }}
              sx={{ flex: '0 0 auto', minHeight: 44, px: 1.25, borderRadius: 1, color: selected ? 'rail.activeText' : 'rail.text', justifyContent: wide ? 'flex-start' : 'center',
                '&.Mui-selected, &.Mui-selected:hover': { bgcolor: 'rail.activeBg' }, '&:hover': { bgcolor: 'rail.activeBg' } }}>
              <ListItemIcon sx={{ minWidth: wide ? 34 : 0, color: 'inherit', position: 'relative' }}>
                <item.icon fontSize="small" />
                {badge && !wide && <Box component="span" aria-hidden sx={{ position: 'absolute', top: -3, right: -5, width: 9, height: 9, borderRadius: 5, bgcolor: '#F2B544' }} />}
              </ListItemIcon>
              {wide && <ListItemText primary={item.label} primaryTypographyProps={{ fontSize: 14, fontWeight: selected ? 500 : 400 }} />}
              {badge && wide && <Box component="span" sx={{ minWidth: 20, height: 20, px: 0.5, borderRadius: 10, bgcolor: '#F2B544', color: '#15171C', fontSize: 12, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{recoveries}</Box>}            </ListItemButton>
          </Tooltip>;
        })}
      </List>
      <Box sx={{ display: 'flex', flexDirection: wide ? 'row' : 'column', alignItems: 'center', gap: 0.5, pt: 1, borderTop: 1, borderColor: 'rail.activeBg' }}>{footer}</Box>
    </Box>
  </Drawer>;
}
