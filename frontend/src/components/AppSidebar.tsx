import React, { useContext, useEffect, useState } from 'react';
import { Box, Button, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, Menu, MenuItem, Tooltip, Typography } from '@mui/material';
import { ChevronLeft, ChevronRight, ExpandLess, ExpandMore, WarningAmber } from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import { allowedSchedulingSections, NavigationUser, SchedulingNavigationContext, sectionUrl, visibleNavigation } from './navigation';
export default function AppSidebar({ user, mobile, expanded, open, onClose, onToggle }: {
  user: NavigationUser; mobile: boolean; expanded: boolean; open: boolean; onClose: () => void; onToggle: () => void;
}) {
  const location = useLocation(); const scheduling = location.pathname === '/scheduling';
  const [sectionsOpen, setSectionsOpen] = useState(scheduling);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const { recoveryActive } = useContext(SchedulingNavigationContext);
  const sections = allowedSchedulingSections(user);
  const section = new URLSearchParams(location.search).get('section') || 'schedules';
  const wide = mobile || expanded;
  useEffect(() => { if (scheduling) setSectionsOpen(true); }, [scheduling]);
  const finish = () => { setAnchor(null); if (mobile) onClose(); };
  const sectionLabel = (id: string, label: string) => <>{label}{id === 'recovery' && recoveryActive && <WarningAmber color="error" fontSize="small" aria-label="Recovery requires attention" sx={{ ml: 1 }} />}</>;
  return <>
    <Drawer variant={mobile ? 'temporary' : 'permanent'} open={mobile ? open : true} onClose={onClose}
      sx={{ width: mobile ? 0 : wide ? 240 : 64, flexShrink: 0, '& .MuiDrawer-paper': { width: mobile ? 280 : wide ? 240 : 64, boxSizing: 'border-box' } }}>
      <Box component="nav" aria-label="Main navigation" sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: wide ? 'space-between' : 'center', minHeight: 56, px: 1 }}>
          {wide && <Typography variant="h6" sx={{ pl: 1 }}>RobotControl</Typography>}
          <IconButton aria-label={mobile ? 'Close navigation' : wide ? 'Collapse navigation' : 'Expand navigation'} onClick={mobile ? onClose : onToggle}>{wide ? <ChevronLeft /> : <ChevronRight />}</IconButton>
        </Box>
        <List sx={{ flex: 1, overflowY: 'auto', px: 1 }}>
          {visibleNavigation(user).map(item => <React.Fragment key={item.path}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <Tooltip title={wide ? '' : item.label} placement="right"><ListItemButton component={item.path === '/scheduling' && !wide ? 'button' : Link}
                to={item.path === '/scheduling' && !wide ? undefined : item.path} aria-label={item.label}
                aria-haspopup={item.path === '/scheduling' && !wide ? 'menu' : undefined} aria-expanded={item.path === '/scheduling' && !wide ? !!anchor : undefined}
                selected={location.pathname === item.path} onClick={event => { if (item.path === '/scheduling' && !wide) setAnchor(event.currentTarget); else finish(); }}
                sx={{ minHeight: 44, px: 1.5, borderRadius: 1, flex: 1 }}>
                <ListItemIcon sx={{ minWidth: wide ? 36 : 24 }}><item.icon color={item.path === '/scheduling' && recoveryActive ? 'error' : 'inherit'} /></ListItemIcon>
                {wide && <ListItemText primary={item.label} />}
              </ListItemButton></Tooltip>
              {wide && item.path === '/scheduling' && <IconButton aria-label="Expand Scheduling sections" aria-expanded={sectionsOpen} onClick={() => setSectionsOpen(value => !value)}>{sectionsOpen ? <ExpandLess /> : <ExpandMore />}</IconButton>}
            </Box>
            {wide && item.path === '/scheduling' && sectionsOpen && <List component="div" disablePadding aria-label="Scheduling sections">
              {sections.map(child => <ListItemButton key={child.id} component={Link} to={sectionUrl(child.index)} selected={scheduling && section === child.id} onClick={finish} sx={{ pl: 5, minHeight: 44, borderRadius: 1 }}>
                <ListItemText primary={sectionLabel(child.id, child.label)} />
              </ListItemButton>)}
            </List>}
          </React.Fragment>)}
        </List>
      </Box>
    </Drawer>
    <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} MenuListProps={{'aria-label': 'Scheduling sections'}}>
      {sections.map(child => <MenuItem key={child.id} component={Link} to={sectionUrl(child.index)} selected={scheduling && section === child.id} onClick={finish}>{sectionLabel(child.id, child.label)}</MenuItem>)}
    </Menu>
  </>;
}
