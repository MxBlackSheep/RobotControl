import React from 'react';
import { Box, Stack, Tab, Tabs, Typography } from '@mui/material';
import { Link, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { allowedSections, moduleSectionUrl, useModuleSection } from './navigation';
import { recoveryCount, useRobotStatusContext } from '../hooks/useRobotStatus';

export function PageContent({ children, reading = false, variant = 'overview' }: { children: React.ReactNode; reading?: boolean; variant?: 'overview' | 'inspection' | 'spatial' | 'task' }) {
  return <Box data-page-pattern={variant} sx={{ width: '100%', minWidth: 0, maxWidth: reading || variant === 'task' ? 1120 : 'none', mx: 'auto', containerType: 'inline-size', containerName: 'workspace' }}>{children}</Box>;
}

/** Title, the module's permitted sections as tabs (kept in `?section=`), and page actions. */
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const sections = allowedSections(pathname, user);
  const [selected] = useModuleSection(pathname, user);
  const recoveries = recoveryCount(useRobotStatusContext().status);
  const tabbed = sections.length > 1;
  return <Box component="header" sx={{ mb: 2 }}>
    <Box sx={{ display: 'flex', alignItems: 'flex-end', columnGap: 3, rowGap: 1, flexWrap: 'wrap', borderBottom: tabbed ? 1 : 0, borderColor: 'divider' }}>
      <Typography component="h1" sx={{ fontSize: { xs: 20, sm: 24 }, fontWeight: 600, lineHeight: 1.3, pb: tabbed ? 1 : 0 }}>{title}</Typography>
      {tabbed && <Tabs value={sections.some(section => section.index === selected) ? selected : false} variant="scrollable" scrollButtons={false}
        aria-label={`${title} sections`} sx={{ flex: '1 1 320px', minWidth: 0, minHeight: 44, mb: '-1px' }}>
        {sections.map(section => <Tab key={section.id} value={section.index} component={Link} to={moduleSectionUrl(pathname, section.index)}
          label={section.id === 'recovery' && recoveries > 0
            ? <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>{section.label}
                <Box component="span" aria-label="requires attention" sx={{ minWidth: 18, height: 18, px: 0.5, borderRadius: 9, bgcolor: '#F2B544', color: '#15171C', fontSize: 11, fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{recoveries}</Box></Box>
            : section.label}
          sx={{ px: 1.5, minWidth: 0 }} />)}
      </Tabs>}
      {actions && <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" sx={{ ml: 'auto', pb: tabbed ? 1 : 0 }}>{actions}</Stack>}
    </Box>
    {description && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{description}</Typography>}
  </Box>;
}
