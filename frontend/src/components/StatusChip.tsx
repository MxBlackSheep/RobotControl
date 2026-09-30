import { Box } from '@mui/material';
import { lightTones, StatusTone } from '../theme';

/** The one status label every screen uses; amber (attention) always means someone must act. */
export default function StatusChip({ tone, label }: { tone: StatusTone; label: string }) {
  return <Box component="span" sx={theme => {
    // Outside the app theme (component tests, embedded previews) fall back to the light tones.
    const colors = theme.palette.tone?.[tone] ?? lightTones[tone];
    return { display: 'inline-flex', alignItems: 'center', height: 24, px: 1.25, borderRadius: 12, fontSize: 13, fontWeight: 500,
      whiteSpace: 'nowrap', bgcolor: colors.bg, color: colors.fg };
  }}>{label}</Box>;
}
