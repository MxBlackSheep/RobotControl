import type { ReactNode } from 'react';
import { Box, Typography } from '@mui/material';
import { layout, touchMedia } from '../theme';

/** Native disclosure: closed initially, with browser keyboard and accessibility semantics. */
export default function Details({ children }: { children: ReactNode }) {
  return <Box component="details" sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
    <Typography component="summary" variant="body2" sx={{ cursor: 'pointer', width: 'fit-content',
      [touchMedia]: { minHeight: layout.touchRow, lineHeight: `${layout.touchRow}px` } }}>Details</Typography>
    {children}
  </Box>;
}
