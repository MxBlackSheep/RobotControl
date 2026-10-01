import { Box } from '@mui/material';
import { layout, lightTones, StatusTone } from '../theme';

/** The one status label every screen uses; amber (attention) always means someone must act. */
export default function StatusChip({ tone, label }: { tone: StatusTone; label: string }) {
  return <Box component="span" sx={theme => {
    // Outside the app theme (component tests, embedded previews) fall back to the light tones.
    const colors = theme.palette.tone?.[tone] ?? lightTones[tone];
    // Like MUI Chip, shrink with an ellipsis rather than widen a narrow page.
    return { display: 'inline-block', maxWidth: '100%', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', verticalAlign: 'middle',
      height: 24, lineHeight: '24px', px: 1, borderRadius: `${layout.radius}px`, fontSize: 12, fontWeight: 600,
      whiteSpace: 'nowrap', bgcolor: colors.bg, color: colors.fg };
  }} title={label}>{label}</Box>;
}
