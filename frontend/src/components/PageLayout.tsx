import React from 'react';
import { Box, Stack, Typography } from '@mui/material';
export function PageContent({ children, reading = false, variant = 'overview' }: { children: React.ReactNode; reading?: boolean; variant?: 'overview' | 'inspection' | 'spatial' | 'task' }) {
  return <Box data-page-pattern={variant} sx={{ width: '100%', minWidth: 0, maxWidth: reading || variant === 'task' ? 1120 : 'none', mx: 'auto', containerType: 'inline-size', containerName: 'workspace' }}>{children}</Box>;
}
export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return <Box component="header" sx={{ mb: 1 }}><Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} flexWrap="wrap">
    <Typography component="h1" variant="h6" sx={{ fontWeight: 700 }}>{title}</Typography>
    {actions && <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap">{actions}</Stack>}
  </Stack>{description && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{description}</Typography>}</Box>;
}
