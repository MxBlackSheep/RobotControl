/**
 * Keyboard Shortcuts Help Component for PyRobot
 * 
 * Displays available keyboard shortcuts to users in a modal dialog
 */

import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Box,
  Chip,
  IconButton,
  useTheme,
  useMediaQuery
} from '@mui/material';
import {
  Close as CloseIcon,
  Keyboard as KeyboardIcon
} from '@mui/icons-material';

interface KeyboardShortcut {
  key: string;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
  description: string;
}

interface KeyboardShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
  shortcuts?: KeyboardShortcut[];
}

const KeyboardShortcutsHelp: React.FC<KeyboardShortcutsHelpProps> = ({
  open,
  onClose,
  shortcuts = []
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  // Default global shortcuts
  const globalShortcuts: KeyboardShortcut[] = [
    { key: '1', altKey: true, description: 'Go to Dashboard' },
    { key: '2', altKey: true, description: 'Go to Database' },
    { key: '3', altKey: true, description: 'Go to Camera' },
    { key: '4', altKey: true, description: 'Go to System Status' },
    { key: '5', altKey: true, description: 'Go to Scheduling' },
    { key: '6', altKey: true, description: 'Go to About' },
    { key: 'H', ctrlKey: true, description: 'Go to Home/Dashboard' },
    { key: 'B', ctrlKey: true, description: 'Go Back' },
    { key: 'R', ctrlKey: true, shiftKey: true, description: 'Refresh Page' },
    { key: '/', description: 'Focus Search/First Input' },
    { key: 'Escape', description: 'Close Dialog/Clear Focus' },
    { key: '?', description: 'Show Keyboard Shortcuts (this dialog)' }
  ];

  const allShortcuts = [...globalShortcuts, ...shortcuts];

  const formatShortcut = (shortcut: KeyboardShortcut) => {
    const parts = [];
    if (shortcut.ctrlKey) parts.push('Ctrl');
    if (shortcut.altKey) parts.push('Alt');
    if (shortcut.shiftKey) parts.push('Shift');
    parts.push(shortcut.key);
    
    return (
      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
        {parts.map((part, index) => (
          <React.Fragment key={part}>
            <Chip
              label={part}
              size="small"
              variant="outlined"
              sx={{
                fontSize: '0.75rem',
                height: 24,
                backgroundColor: theme.palette.grey[100]
              }}
            />
            {index < parts.length - 1 && (
              <Typography variant="body2" sx={{ alignSelf: 'center' }}>
                +
              </Typography>
            )}
          </React.Fragment>
        ))}
      </Box>
    );
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      fullScreen={isMobile}
      PaperProps={{
        sx: {
          ...(isMobile && {
            m: 0,
            borderRadius: 0,
            maxHeight: '100%'
          })
        }
      }}
    >
      <DialogTitle
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          pr: 1
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          <KeyboardIcon sx={{ mr: 1 }} />
          <Typography variant="h6">Keyboard Shortcuts</Typography>
        </Box>
        
        <IconButton
          onClick={onClose}
          size="small"
          aria-label="Close shortcuts help"
          sx={{
            minWidth: 44,
            minHeight: 44
          }}
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ p: { xs: 2, sm: 3 } }}>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          Use these keyboard shortcuts to navigate PyRobot more efficiently:
        </Typography>

        <TableContainer 
          component={Paper} 
          variant="outlined"
          sx={{ mt: 2 }}
        >
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ fontWeight: 600 }}>
                  Shortcut
                </TableCell>
                <TableCell sx={{ fontWeight: 600 }}>
                  Description
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {allShortcuts.map((shortcut, index) => (
                <TableRow key={index}>
                  <TableCell sx={{ minWidth: { xs: 120, sm: 150 } }}>
                    {formatShortcut(shortcut)}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2">
                      {shortcut.description}
                    </Typography>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        <Box sx={{ mt: 3, p: 2, backgroundColor: 'info.light', borderRadius: 1 }}>
          <Typography variant="body2" sx={{ fontSize: '0.875rem' }}>
            <strong>Accessibility Tips:</strong>
            <br />
            • Use Tab to navigate between interactive elements
            <br />
            • Use Arrow keys to navigate within lists and menus  
            <br />
            • Use Enter or Space to activate buttons and links
            <br />
            • Use Escape to close dialogs and clear focus
          </Typography>
        </Box>
      </DialogContent>

      <DialogActions sx={{ p: { xs: 2, sm: 3 } }}>
        <Button 
          onClick={onClose}
          sx={{
            minHeight: { xs: 44, sm: 36 }
          }}
        >
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
};

// Hook to manage keyboard shortcuts help dialog
export const useKeyboardShortcutsHelp = () => {
  const [open, setOpen] = useState(false);

  const showHelp = () => setOpen(true);
  const hideHelp = () => setOpen(false);

  // Listen for ? key to show help
  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === '?' && !event.ctrlKey && !event.altKey) {
        const activeElement = document.activeElement as HTMLElement | null;
        const isInputField = activeElement && (
          activeElement.tagName === 'INPUT' ||
          activeElement.tagName === 'TEXTAREA' ||
          activeElement.isContentEditable
        );
        
        if (!isInputField) {
          event.preventDefault();
          showHelp();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, []);

  return {
    open,
    showHelp,
    hideHelp
  };
};

export default KeyboardShortcutsHelp;
