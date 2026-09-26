import { createTheme } from '@mui/material/styles';
import type { PaletteMode } from '@mui/material';

export function createAppTheme(mode: PaletteMode) {
  const dark = mode === 'dark';
  const focus = { outline: '3px solid', outlineColor: dark ? '#90caf9' : '#1565c0', outlineOffset: 2 };
  const touch = { '@media (pointer: coarse), (max-width: 600px)': { minHeight: 44, minWidth: 44 } };
  return createTheme({
    palette: {
      mode,
      primary: { main: dark ? '#90caf9' : '#1565c0' },
      secondary: { main: dark ? '#ef9a9a' : '#c62828' },
      success: { main: dark ? '#81c784' : '#2e7d32' },
      warning: { main: dark ? '#ffb74d' : '#a54b00' },
      error: { main: dark ? '#ef9a9a' : '#c62828' },
      info: { main: dark ? '#81d4fa' : '#0277bd' },
      background: { default: dark ? '#101820' : '#f5f7fa', paper: dark ? '#19232d' : '#ffffff' },
    },
    typography: {
      fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
      h4: { fontWeight: 600 }, h5: { fontWeight: 600 }, h6: { fontWeight: 600 },
    },
    components: {
      MuiCssBaseline: { styleOverrides: {
        ':root': { colorScheme: mode },
        body: { overflowWrap: 'break-word' },
        '*': { scrollbarColor: dark ? '#607080 #19232d' : '#a3adba #f5f7fa' },
        '*:focus-visible': focus,
      } },
      MuiButton: { styleOverrides: { root: { textTransform: 'none', minHeight: 36, ...touch, '&:focus-visible': focus } } },
      MuiIconButton: { styleOverrides: { root: { ...touch, '&:focus-visible': focus } } },
      MuiInputBase: { styleOverrides: { root: { '@media (pointer: coarse), (max-width: 600px)': { minHeight: 44 } } } },
      MuiMenuItem: { styleOverrides: { root: touch } },
      MuiTab: { styleOverrides: { root: { textTransform: 'none', minHeight: 44 } } },
      MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
      MuiTableCell: { styleOverrides: { head: { backgroundColor: dark ? '#22313f' : '#edf1f5', fontWeight: 600 } } },
      MuiDialog: { styleOverrides: { paper: { '&:not(.MuiDialog-paperFullScreen)': { '@media (max-width: 600px)': { margin: 8, maxWidth: 'calc(100% - 16px)' } } } } },
    },
  });
}

export default createAppTheme('light');
