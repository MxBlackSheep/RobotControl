import React, { createContext, useCallback, useEffect, useState } from 'react';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useSearchParams } from 'react-router-dom';
import { Dashboard, Storage, Schedule, Videocam, Science, Build, Description, MonitorHeart, AdminPanelSettings, Info } from '@mui/icons-material';
export type NavigationUser = { role?: string; session_is_local?: boolean } | null;
export const isLocalUser = (user: NavigationUser) => typeof user?.session_is_local === 'boolean' ? user.session_is_local : ['localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'].includes(window.location.hostname);
export const schedulingSections = [
  { id: 'schedules', label: 'Schedules', index: 0 }, { id: 'methods', label: 'Methods', index: 6, local: true },
  { id: 'calendar', label: 'Calendar', index: 2 }, { id: 'history', label: 'History', index: 3 },
  { id: 'archived', label: 'Archived', index: 4 }, { id: 'recovery', label: 'Recovery', index: 1 },
  { id: 'notifications', label: 'Notifications', index: 5, admin: true },
];
export const allowedSchedulingSections = (user: NavigationUser) => ['admin', 'user'].includes(user?.role || '') ? schedulingSections.filter(section => (!section.admin || user?.role === 'admin') && (!section.local || isLocalUser(user))) : [];
export const sectionUrl = (index: number) => index === 0 ? '/scheduling' : `/scheduling?section=${schedulingSections.find(section => section.index === index)?.id || 'schedules'}`;
export const navigationItems = [
  { label: 'Dashboard', path: '/', icon: Dashboard }, { label: 'Database', path: '/database', icon: Storage },
  { label: 'Scheduling', path: '/scheduling', icon: Schedule, roles: ['admin', 'user'] },
  { label: 'Camera', path: '/camera', icon: Videocam }, { label: 'Labware', path: '/labware', icon: Science, roles: ['admin', 'user'] },
  { label: 'Maintenance', path: '/maintenance', icon: Build }, { label: 'LogFile', path: '/logfile', icon: Description },
  { label: 'System Status', path: '/system-status', icon: MonitorHeart }, { label: 'Admin', path: '/admin', icon: AdminPanelSettings, roles: ['admin'] },
  { label: 'About', path: '/about', icon: Info },
];
export const visibleNavigation = (user: NavigationUser) => navigationItems.filter(item => !item.roles || item.roles.includes(user?.role || ''));
export const SchedulingNavigationContext = createContext({ recoveryActive: false, setRecoveryActive: (_active: boolean) => {} });
export function useSchedulingSection(user: NavigationUser) {
  const [params, setParams] = useSearchParams();
  const value = params.get('section');
  const selected = allowedSchedulingSections(user).find(section => section.id === value);
  useEffect(() => {
    if (value && !selected) setParams(previous => { const next = new URLSearchParams(previous); next.delete('section'); return next; }, {replace: true});
  }, [value, selected?.id, setParams]);
  const change = useCallback((index: number) => setParams(previous => {
    const next = new URLSearchParams(previous);
    const section = schedulingSections.find(section => section.index === index);
    if (!section || index === 0) next.delete('section'); else next.set('section', section.id);
    return next;
  }), [setParams]);
  return [selected?.index || 0, change] as const;
}

export function useSidebarLayout() {
  const mobile = useMediaQuery('(max-width:899.95px)');
  const large = useMediaQuery('(min-width:1440px)');
  const [saved, setSaved] = useState<boolean | null>(() => {
    try { const value = localStorage.getItem('robotcontrol.sidebar.expanded'); return value === 'true' ? true : value === 'false' ? false : null; }
    catch { return null; }
  });
  const expanded = saved ?? large;
  const toggle = () => { const next = !expanded; setSaved(next); try { localStorage.setItem('robotcontrol.sidebar.expanded', String(next)); } catch { /* Keep the in-memory preference. */ } };
  return {mobile, expanded, toggle};
}
