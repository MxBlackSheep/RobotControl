import { createTheme } from '@mui/material/styles';
import type { PaletteMode } from '@mui/material';

export type StatusTone = 'running' | 'completed' | 'neutral' | 'attention' | 'fault';
type ToneColors = { bg: string; fg: string };

declare module '@mui/material/styles' {
  interface Palette {
    rail: { bg: string; text: string; activeBg: string; activeText: string; muted: string };
    tone: Record<StatusTone, ToneColors>;
  }
  interface PaletteOptions {
    rail?: Palette['rail'];
    tone?: Palette['tone'];
  }
}

export const lightTones: Record<StatusTone, ToneColors> = {
  running: { bg: '#E6EEFA', fg: '#1D4F99' }, completed: { bg: '#E5F3EA', fg: '#17663A' },
  neutral: { bg: '#EEF0F3', fg: '#3F4550' }, attention: { bg: '#FDF0D5', fg: '#7A4200' }, fault: { bg: '#FCE8E6', fg: '#A3261B' },
};

export const fontSans = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif';
export const fontMono = '"IBM Plex Mono", Consolas, "Courier New", monospace';

export function createAppTheme(mode: PaletteMode) {
  const dark = mode === 'dark';
  const primary = dark ? '#7FB0F0' : '#1D5FB8';
  const focus = { outline: '3px solid', outlineColor: primary, outlineOffset: 2 };
  const touch = { '@media (pointer: coarse), (max-width: 600px)': { minHeight: 44, minWidth: 44 } };
  const divider = dark ? '#2A303A' : '#DCDFE3';
  return createTheme({
    palette: {
      mode,
      primary: { main: primary, contrastText: dark ? '#0B0D10' : '#FFFFFF' },
      secondary: { main: dark ? '#C9CED6' : '#15171C' },
      success: { main: dark ? '#86D19E' : '#1B7A45' },
      warning: { main: dark ? '#F2C470' : '#9A5B00' },
      error: { main: dark ? '#F4A097' : '#B42318' },
      info: { main: primary },
      background: { default: dark ? '#101318' : '#F3F4F1', paper: dark ? '#181C23' : '#FFFFFF' },
      text: { primary: dark ? '#E8EAED' : '#15171C', secondary: dark ? '#B8BEC8' : '#4A505C' },
      divider,
      rail: dark
        ? { bg: '#0B0D10', text: '#B8BEC8', activeBg: '#232833', activeText: '#FFFFFF', muted: '#8B93A1' }
        : { bg: '#15171C', text: '#B8BEC8', activeBg: '#2A2F3A', activeText: '#FFFFFF', muted: '#9AA1AD' },
      tone: dark ? {
        running: { bg: '#1B2A40', fg: '#9CC3F5' }, completed: { bg: '#16301F', fg: '#86D19E' },
        neutral: { bg: '#252A33', fg: '#C9CED6' }, attention: { bg: '#3A2A10', fg: '#F2C470' }, fault: { bg: '#3B1A17', fg: '#F4A097' },
      } : lightTones,
    },
    shape: { borderRadius: 6 },
    typography: {
      fontFamily: fontSans,
      h4: { fontWeight: 600 }, h5: { fontWeight: 600 }, h6: { fontWeight: 600 },
      button: { fontWeight: 500 },
    },
    components: {
      MuiCssBaseline: { styleOverrides: {
        ':root': { colorScheme: mode },
        body: { overflowWrap: 'break-word' },
        '*': { scrollbarColor: dark ? '#4A5260 #181C23' : '#A3ADBA #F3F4F1' },
        '*:focus-visible': focus,
        'code, kbd, pre, samp': { fontFamily: fontMono },
      } },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: { root: { textTransform: 'none', minHeight: 36, ...touch, '&:focus-visible': focus } },
      },
      MuiIconButton: { styleOverrides: { root: { ...touch, '&:focus-visible': focus } } },
      MuiInputBase: { styleOverrides: { root: { '@media (pointer: coarse), (max-width: 600px)': { minHeight: 44 } } } },
      MuiMenuItem: { styleOverrides: { root: touch } },
      MuiTab: { styleOverrides: { root: { textTransform: 'none', minHeight: 44, fontSize: 14 } } },
      MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' } } },
      MuiCard: { defaultProps: { variant: 'outlined' }, styleOverrides: { root: { borderRadius: 8 } } },
      MuiTableCell: { styleOverrides: { head: { backgroundColor: dark ? '#1F242D' : '#F6F7F8', fontWeight: 600 } } },
      MuiDialog: { styleOverrides: { paper: { '&:not(.MuiDialog-paperFullScreen)': { '@media (max-width: 600px)': { margin: 8, maxWidth: 'calc(100% - 16px)' } } } } },
    },
  });
}

export default createAppTheme('light');
