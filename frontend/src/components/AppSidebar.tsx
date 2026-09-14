import React, { useContext, useEffect, useState } from 'react';
import { Box, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, Menu, MenuItem, Tooltip, Typography } from '@mui/material';
import { ChevronLeft, ChevronRight, ExpandLess, ExpandMore, WarningAmber } from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import { allowedSections, NavigationUser, SchedulingNavigationContext, moduleSectionUrl, visibleNavigation } from './navigation';
export default function AppSidebar({ user, mobile, expanded, open, onClose, onToggle }: {
  user: NavigationUser; mobile: boolean; expanded: boolean; open: boolean; onClose: () => void; onToggle: () => void;
}) {
  const location = useLocation();
  const [sectionsOpen, setSectionsOpen] = useState<Record<string, boolean>>({[location.pathname]: true});
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const { recoveryActive } = useContext(SchedulingNavigationContext);
  const [menuPath, setMenuPath] = useState('/scheduling');
  const sections = allowedSections(menuPath, user);
  const section = new URLSearchParams(location.search).get('section') || allowedSections(location.pathname, user)[0]?.id;
  const wide = mobile || expanded;
  useEffect(() => { setSectionsOpen(previous => ({...previous, [location.pathname]: true})); }, [location.pathname]);
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
          {visibleNavigation(user).map(item => { const children = allowedSections(item.path, user); const grouped = children.length > 0; return <React.Fragment key={item.path}>
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <Tooltip title={wide ? '' : item.label} placement="right"><ListItemButton component={grouped && !wide ? 'button' : Link}
                to={grouped && !wide ? undefined : item.path} aria-label={item.label}
                aria-haspopup={grouped && !wide ? 'menu' : undefined} aria-expanded={grouped && !wide ? !!anchor && menuPath === item.path : undefined}
                selected={location.pathname === item.path} onClick={event => { if (grouped && !wide) { setMenuPath(item.path); setAnchor(event.currentTarget); } else finish(); }}
                sx={{ minHeight: 44, px: 1.5, borderRadius: 1, flex: 1 }}>
                <ListItemIcon sx={{ minWidth: wide ? 36 : 24 }}><item.icon color={item.path === '/scheduling' && recoveryActive ? 'error' : 'inherit'} /></ListItemIcon>
                {wide && <ListItemText primary={item.label} />}
              </ListItemButton></Tooltip>
              {wide && grouped && <IconButton aria-label={`${sectionsOpen[item.path] ? 'Collapse' : 'Expand'} ${item.label} sections`} aria-expanded={!!sectionsOpen[item.path]} onClick={() => setSectionsOpen(value => ({...value, [item.path]: !value[item.path]}))}>{sectionsOpen[item.path] ? <ExpandLess /> : <ExpandMore />}</IconButton>}
            </Box>
            {wide && grouped && sectionsOpen[item.path] && <List component="div" disablePadding aria-label={`${item.label} sections`}>
              {children.map(child => <ListItemButton key={child.id} component={Link} to={moduleSectionUrl(item.path, child.index)} selected={location.pathname === item.path && section === child.id} onClick={finish} sx={{ pl: 5, minHeight: 44, borderRadius: 1 }}>
                <ListItemText primary={sectionLabel(child.id, child.label)} />
              </ListItemButton>)}
            </List>}
          </React.Fragment>; })}
        </List>
      </Box>
    </Drawer>
    <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)} MenuListProps={{'aria-label': `${visibleNavigation(user).find(item => item.path === menuPath)?.label} sections`}}>
      {sections.map(child => <MenuItem key={child.id} component={Link} to={moduleSectionUrl(menuPath, child.index)} selected={location.pathname === menuPath && section === child.id} onClick={finish}>{sectionLabel(child.id, child.label)}</MenuItem>)}
    </Menu>
  </>;
}
