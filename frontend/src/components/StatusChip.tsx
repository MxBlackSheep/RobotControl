import { Box } from '@mui/material';
import type { StatusTone } from '../theme';

/** The one status label every screen uses; amber (attention) always means someone must act. */
export default function StatusChip({ tone, label }: { tone: StatusTone; label: string }) {
  return <Box component="span" sx={theme => ({
    display: 'inline-flex', alignItems: 'center', height: 24, px: 1.25, borderRadius: 12, fontSize: 13, fontWeight: 500,
    whiteSpace: 'nowrap', bgcolor: theme.palette.tone[tone].bg, color: theme.palette.tone[tone].fg,
  })}>{label}</Box>;
}
