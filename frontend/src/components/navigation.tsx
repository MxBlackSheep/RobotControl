import { useCallback, useEffect, useState } from 'react';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useSearchParams } from 'react-router-dom';
import { Dashboard, Storage, Schedule, Videocam, Science, Build, Description, MonitorHeart, AdminPanelSettings } from '@mui/icons-material';
export type NavigationUser = { role?: string; session_is_local?: boolean } | null;
/** Roles that may open a page; any other page is open to every signed-in role. The server still refuses what a role may not do. */
const pageRoles: Record<string, string[]> = { '/scheduling': ['admin', 'user'], '/pyhsl': ['admin', 'user'], '/labware': ['admin', 'user'], '/admin': ['admin'] };
export const canOpen = (path: string, user: NavigationUser) => !pageRoles[path] || pageRoles[path].includes(user?.role || '');
/** The server's answer for this session (lab PC or tunnel); with no answer the session only watches. */
export const isLocalUser = (user: NavigationUser) => user?.session_is_local === true;
export const schedulingSections = [
  { id: 'schedules', label: 'Schedules', index: 0 }, { id: 'methods', label: 'Methods', index: 6, local: true },
  { id: 'calendar', label: 'Calendar', index: 2 }, { id: 'history', label: 'History', index: 3 },
  { id: 'archived', label: 'Archived', index: 4 }, { id: 'recovery', label: 'Recovery', index: 1 },
  { id: 'notifications', label: 'Notifications', index: 5, admin: true },
];
/** `source` names the log source a Logs section shows. */
export type Section = {id: string; label: string; index: number; local?: boolean; admin?: boolean; adminOrLocal?: boolean; source?: string};
export const sectionRegistry: Record<string, Section[]> = {
  '/scheduling': schedulingSections,
  '/database': [{id: 'tables', label: 'Tables', index: 0}, {id: 'procedures', label: 'Stored procedures', index: 1}, {id: 'restore', label: 'Restore', index: 2, adminOrLocal: true}, {id: 'operations', label: 'Operations', index: 3, local: true, admin: true}, {id: 'retrieval', label: 'Data retrieval', index: 4}, {id: 'packages', label: 'Manage packages', index: 5, local: true, admin: true}, {id: 'settings', label: 'Database settings', index: 6, local: true, admin: true}],
  '/camera': [{id: 'live', label: 'Live view', index: 0}, {id: 'archive', label: 'Video archive', index: 1}],
  '/labware': [{id: 'tips', label: 'Tip tracking', index: 0}, {id: 'cytomat', label: 'Cytomat', index: 1}],
  '/logfile': [{id: 'python', label: 'Python logs', index: 0, source: 'python_log'}, {id: 'hamilton', label: 'Hamilton traces', index: 1, source: 'hamilton_logfiles'}, {id: 'robotcontrol', label: 'RobotControl logs', index: 2, adminOrLocal: true, source: 'robotcontrol_logs'}],
  '/admin': [{id: 'users', label: 'User accounts', index: 0}, {id: 'password-resets', label: 'Password reset requests', index: 1}, {id: 'storage', label: 'Storage health', index: 2, local: true}],
};
const roleAllows = (section: Section, user: NavigationUser) => !section.admin || user?.role === 'admin';
/** Whether this user has the section only on the RobotControl computer. */
const needsLocal = (section: Section, user: NavigationUser) => section.local || (section.adminOrLocal && user?.role !== 'admin');
export const allowedSections = (path: string, user: NavigationUser) => {
  if (!canOpen(path, user)) return [];
  return (sectionRegistry[path] || []).filter(section => roleAllows(section, user) && (!needsLocal(section, user) || isLocalUser(user)));
};
/** Sections this user would have on the RobotControl computer but a remote session (the tunnel) lacks. */
export const localOnlySections = (path: string, user: NavigationUser) => {
  if (!user || isLocalUser(user) || !canOpen(path, user)) return [];
  return (sectionRegistry[path] || []).filter(section => roleAllows(section, user) && needsLocal(section, user));
};
export const allowedSchedulingSections = (user: NavigationUser) => allowedSections('/scheduling', user);
export const moduleSectionUrl = (path: string, index: number) => index === 0 ? path : `${path}?section=${sectionRegistry[path]?.find(section => section.index === index)?.id || ''}`;
export const navigationItems = [
  { label: 'Overview', path: '/', icon: Dashboard }, { label: 'Database', path: '/database', icon: Storage },
  { label: 'Scheduling', path: '/scheduling', icon: Schedule },
  { label: 'Camera', path: '/camera', icon: Videocam }, { label: 'Labware', path: '/labware', icon: Science },
  { label: 'Maintenance', path: '/maintenance', icon: Build }, { label: 'Logs', path: '/logfile', icon: Description },
  { label: 'System status', path: '/system-status', icon: MonitorHeart }, { label: 'Admin', path: '/admin', icon: AdminPanelSettings },
];
export const visibleNavigation = (user: NavigationUser) => navigationItems.filter(item => canOpen(item.path, user));

/*
 * Phones (below 900px) are a monitor: through the tunnel the server refuses robot and lab changes,
 * so the phone shows four fixed tabs and a More list of read-only places instead of every module.
 */
type PhoneLink = { label: string; to: string };
const permitted = (user: NavigationUser) => (item: PhoneLink) => canOpen(item.to.split('?')[0], user);
export const phoneTabs: (PhoneLink & { id: 'now' | 'runs' | 'camera' | 'more' })[] = [
  { id: 'now', label: 'Now', to: '/' }, { id: 'runs', label: 'Runs', to: '/scheduling' },
  { id: 'camera', label: 'Camera', to: '/camera' }, { id: 'more', label: 'More', to: '/more' },
];
export const visiblePhoneTabs = (user: NavigationUser) => phoneTabs.filter(permitted(user));
/** Pages a tab opens itself (What happened is Now's); anything else is reached from More. */
const tabPages: Record<string, 'now'> = { '/held': 'now', '/pyhsl': 'now' };
/** The tab a path belongs to: every page that is not a tab's own is reached from More. */
export const phoneTabFor = (path: string) => phoneTabs.find(tab => tab.to === path && tab.id !== 'more')?.id ?? tabPages[path] ?? 'more';
/** Where a phone page's back link leads: the tab that opened it, or none for a tab's own page. */
export const phoneBack = (path: string) => {
  if (phoneTabs.some(tab => tab.to === path)) return null;
  const tab = phoneTabs.find(item => item.id === phoneTabFor(path))!;
  return { label: tab.label, to: tab.to };
};
export const moreItems: PhoneLink[] = [
  { label: 'Tip racks', to: '/labware' }, { label: 'Cytomat', to: '/labware?section=cytomat' },
  { label: 'Run logs', to: '/logfile?section=hamilton' }, { label: 'Database tables', to: '/database' },
  { label: 'Reports', to: '/database?section=retrieval' }, { label: 'System status', to: '/system-status' }, { label: 'Account', to: '/account' },
];
export const visibleMoreItems = (user: NavigationUser) => moreItems.filter(permitted(user));
/** The More entry for a page and section, so the page is titled with the name that was tapped. */
export const moreItemFor = (path: string, sectionId: string | undefined) => moreItems.find(item => {
  const [itemPath, query = ''] = item.to.split('?');
  return itemPath === path && (new URLSearchParams(query).get('section') ?? undefined) === sectionId;
});
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
