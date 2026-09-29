import React from 'react';
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';

import { Shortcut, SHORTCUT_HELP } from '../hooks/useKeyboardNavigation';

const keysOf = (shortcut: Shortcut) => [
  ...(shortcut.ctrl ? ['Ctrl'] : []),
  ...(shortcut.alt ? ['Alt'] : []),
  ...(shortcut.shift ? ['Shift'] : []),
  shortcut.key.length === 1 ? shortcut.key.toUpperCase() : shortcut.key,
];

const KeyboardShortcutsHelp: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  const isMobile = useMediaQuery(useTheme().breakpoints.down('sm'));

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth fullScreen={isMobile}>
      <DialogTitle>Keyboard Shortcuts</DialogTitle>
      <DialogContent dividers>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 600 }}>Shortcut</TableCell>
              <TableCell sx={{ fontWeight: 600 }}>Description</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {SHORTCUT_HELP.map(shortcut => (
              <TableRow key={shortcut.description}>
                <TableCell>
                  <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                    {keysOf(shortcut).map(key => <Chip key={key} label={key} size="small" variant="outlined" />)}
                  </Box>
                </TableCell>
                <TableCell>{shortcut.description}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          Tab moves between controls, arrow keys move within lists and menus, and Enter or Space activates.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={{ minHeight: 44 }}>Close</Button>
      </DialogActions>
    </Dialog>
  );
};

export default KeyboardShortcutsHelp;
