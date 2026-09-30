import React from 'react';
import { Box, Stack, Tab, Tabs, Typography } from '@mui/material';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { allowedSections, moduleSectionUrl, useModuleSection } from './navigation';
import { robotAttention, useRobotStatusContext } from '../hooks/useRobotStatus';
import { panelPadding } from '../theme';

export function PageContent({ children, reading = false, variant = 'overview' }: { children: React.ReactNode; reading?: boolean; variant?: 'overview' | 'inspection' | 'spatial' | 'task' }) {
  return <Box data-page-pattern={variant} sx={{ width: '100%', minWidth: 0, maxWidth: reading || variant === 'task' ? 1120 : variant === 'overview' ? 1440 : 'none', mx: 'auto', containerType: 'inline-size', containerName: 'workspace' }}>{children}</Box>;
}

/** Title, the module's permitted sections as tabs (kept in `?section=`), and page actions. */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const sections = allowedSections(pathname, user);
  const [selected] = useModuleSection(pathname, user);
  const attention = robotAttention(useRobotStatusContext().status);
  const tabbed = sections.length > 1;
  return <Box component="header" sx={{ mb: 2 }}>
    <Box sx={{ display: 'flex', alignItems: 'center', minHeight: 36, columnGap: 3, rowGap: 1, flexWrap: 'wrap' }}>
      <Typography component="h1" sx={{ fontSize: { xs: 20, sm: 24 }, fontWeight: 600, lineHeight: 1.3 }}>{title}</Typography>
      {actions && <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ ml: 'auto' }}>{actions}</Stack>}
    </Box>
    {description && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{description}</Typography>}
    {tabbed && <Tabs value={sections.some(section => section.index === selected) ? selected : false} variant="scrollable" scrollButtons={false}
        aria-label={`${title} sections`} sx={{ mt: 1, minWidth: 0, minHeight: 44, borderBottom: 1, borderColor: 'divider' }}>
        {sections.map(section => <Tab key={section.id} value={section.index} component={Link} to={moduleSectionUrl(pathname, section.index)}
          label={section.id === 'recovery' && attention
            ? <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>{section.label}
                <Box component="span" aria-label="requires attention" sx={{ minWidth: 18, height: 18, px: 0.5, borderRadius: 9, bgcolor: '#F2B544', color: '#15171C', fontSize: 11, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{attention.kind === 'recovery' ? attention.count : '!'}</Box></Box>
            : section.label}
          sx={{ px: 1.5, minWidth: 0 }} />)}
      </Tabs>}
  </Box>;
}

/** Heading/action alignment; the parent owns spacing between header and content. */
export function PanelHeader({ title, actions }: { title: string; actions?: React.ReactNode }) {
  return <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} flexWrap="wrap" sx={{ minHeight: 36 }}>
    <Typography component="h2" variant="h6">{title}</Typography>
    {actions}
  </Stack>;
}

/** Small uppercase label that names a status panel ("NOW RUNNING", "RESOURCE USE"). */
export function PanelLabel({ children, component = 'h2' }: { children: React.ReactNode; component?: React.ElementType }) {
  return <Typography component={component} sx={{ fontSize: 12, fontWeight: 600, letterSpacing: 0.8, textTransform: 'uppercase', color: 'text.secondary', lineHeight: 1.5 }}>{children}</Typography>;
}

/** The name of the selected item in a detail panel (a schedule, a folder, a recovery). */
export function DetailTitle({ children, component = 'h2' }: { children: React.ReactNode; component?: React.ElementType }) {
  return <Typography component={component} sx={{ fontSize: 18, fontWeight: 600, lineHeight: 1.4, overflowWrap: 'anywhere', minWidth: 0 }}>{children}</Typography>;
}

/** A detail panel with nothing chosen yet: a plain prompt, not an alert. */
export function EmptyPanel({ children }: { children: React.ReactNode }) {
  return <Box sx={{ flex: 1, p: panelPadding, bgcolor: 'background.paper', border: 1, borderColor: 'divider', borderRadius: 2 }}>
    <Typography color="text.secondary">{children}</Typography>
  </Box>;
}
