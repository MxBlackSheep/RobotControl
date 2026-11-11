import { Typography } from '@mui/material';

/** A stored record's review reason, as the row's second line beside a "Needs review" StatusChip. */
export default function ReviewReason({ reason }: { reason: string }) {
  return <Typography sx={{ fontSize: 12, lineHeight: '16px', color: theme => theme.palette.tone.attention.fg,
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{reason}</Typography>;
}
