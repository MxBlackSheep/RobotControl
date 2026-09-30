import { useCallback, useEffect, useState } from 'react';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useSearchParams } from 'react-router-dom';
import { Dashboard, Storage, Schedule, Videocam, Science, Build, Description, MonitorHeart, AdminPanelSettings } from '@mui/icons-material';
export type NavigationUser = { role?: string; session_is_local?: boolean } | null;
export const isLocalUser = (user: NavigationUser) => typeof user?.session_is_local === 'boolean' ? user.session_is_local : ['localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0'].includes(window.location.hostname);
export const schedulingSections = [
  { id: 'schedules', label: 'Schedules', index: 0 }, { id: 'methods', label: 'Methods', index: 6, local: true },
  { id: 'calendar', label: 'Calendar', index: 2 }, { id: 'history', label: 'History', index: 3 },
  { id: 'archived', label: 'Archived', index: 4 }, { id: 'recovery', label: 'Recovery', index: 1 },
  { id: 'notifications', label: 'Notifications', index: 5, admin: true },
];
export type Section = {id: string; label: string; index: number; local?: boolean; admin?: boolean; adminOrLocal?: boolean};
export const sectionRegistry: Record<string, Section[]> = {
  '/scheduling': schedulingSections,
  '/database': [{id: 'tables', label: 'Tables', index: 0}, {id: 'procedures', label: 'Stored procedures', index: 1}, {id: 'restore', label: 'Restore', index: 2, adminOrLocal: true}, {id: 'operations', label: 'Operations', index: 3, local: true, admin: true}, {id: 'retrieval', label: 'Data retrieval', index: 4}, {id: 'packages', label: 'Manage packages', index: 5, local: true, admin: true}, {id: 'settings', label: 'Database settings', index: 6, local: true, admin: true}],
  '/camera': [{id: 'archive', label: 'Video archive', index: 0}, {id: 'live', label: 'Live streaming', index: 1}],
  '/labware': [{id: 'tips', label: 'Tip tracking', index: 0}, {id: 'cytomat', label: 'Cytomat', index: 1}],
  '/logfile': [{id: 'python', label: 'Python logs', index: 0}, {id: 'hamilton', label: 'Hamilton traces', index: 1}, {id: 'robotcontrol', label: 'RobotControl logs', index: 2, adminOrLocal: true}],
  '/admin': [{id: 'users', label: 'User accounts', index: 0}, {id: 'password-resets', label: 'Password reset requests', index: 1}, {id: 'storage', label: 'Storage health', index: 2, local: true}],
};
export const allowedSections = (path: string, user: NavigationUser) => {
  if ((['/scheduling', '/labware'].includes(path) && !['admin', 'user'].includes(user?.role || '')) || (path === '/admin' && user?.role !== 'admin')) return [];
  return (sectionRegistry[path] || []).filter(section => (!section.admin || user?.role === 'admin') && (!section.local || isLocalUser(user)) && (!section.adminOrLocal || user?.role === 'admin' || isLocalUser(user)));
};
export const allowedSchedulingSections = (user: NavigationUser) => allowedSections('/scheduling', user);
export const moduleSectionUrl = (path: string, index: number) => index === 0 ? path : `${path}?section=${sectionRegistry[path]?.find(section => section.index === index)?.id || ''}`;
export const navigationItems = [
  { label: 'Overview', path: '/', icon: Dashboard }, { label: 'Database', path: '/database', icon: Storage },
  { label: 'Scheduling', path: '/scheduling', icon: Schedule, roles: ['admin', 'user'] },
  { label: 'Camera', path: '/camera', icon: Videocam }, { label: 'Labware', path: '/labware', icon: Science, roles: ['admin', 'user'] },
  { label: 'Maintenance', path: '/maintenance', icon: Build }, { label: 'Logs', path: '/logfile', icon: Description },
  { label: 'System Status', path: '/system-status', icon: MonitorHeart }, { label: 'Admin', path: '/admin', icon: AdminPanelSettings, roles: ['admin'] },
];
export const visibleNavigation = (user: NavigationUser) => navigationItems.filter(item => !item.roles || item.roles.includes(user?.role || ''));
export function useModuleSection(path: string, user: NavigationUser) {
  const [params, setParams] = useSearchParams();
  const value = params.get('section');
  const permitted = allowedSections(path, user);
  const selected = permitted.find(section => section.id === value);
  useEffect(() => {
    if (value && !selected) setParams(previous => { const next = new URLSearchParams(previous); next.delete('section'); return next; }, {replace: true});
  }, [value, selected?.id, setParams]);
  const change = useCallback((index: number) => setParams(previous => {
    const next = new URLSearchParams(previous);
    const section = allowedSections(path, user).find(section => section.index === index);
    if (!section || index === 0) next.delete('section'); else next.set('section', section.id);
    return next;
  }), [path, user?.role, user?.session_is_local, setParams]);
  return [selected?.index ?? permitted[0]?.index ?? 0, change] as const;
}
export const useSchedulingSection = (user: NavigationUser) => useModuleSection('/scheduling', user);

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
