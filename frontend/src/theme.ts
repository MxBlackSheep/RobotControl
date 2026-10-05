import { createTheme } from '@mui/material/styles';
import type { PaletteMode } from '@mui/material';

/**
 * Design system A ("instrument console"). Every size is a multiple of the 4px unit and every
 * page is built from these tokens through the primitives in components/PageLayout.tsx.
 * Light and dark share the structure; only the palette changes.
 */
export type StatusTone = 'running' | 'completed' | 'neutral' | 'attention' | 'fault';
type ToneColors = { bg: string; fg: string; dot: string };
type Surface = { head: string; headLine: string; rowLine: string; track: string; label: string; control: string };
type Attention = { line: string; head: string; text: string; action: string; actionText: string };

declare module '@mui/material/styles' {
  interface Palette {
    rail: { bg: string; text: string; activeBg: string; activeText: string; muted: string };
    tone: Record<StatusTone, ToneColors>;
    surface: Surface;
    attentionSurface: Attention;
  }
  interface PaletteOptions {
    rail?: Palette['rail'];
    tone?: Palette['tone'];
    surface?: Surface;
    attentionSurface?: Attention;
  }
}

/** Layout tokens in px. Pages use these through the primitives, never their own numbers. */
export const layout = {
  unit: 4,
  page: 24,
  pagePhone: 16,
  gutter: 12,
  inset: 16,
  header: 40,
  row: 40,
  touchRow: 44,
  control: 36,
  rail: 216,
  railCollapsed: 64,
  radius: 4,
} as const;

export const lightTones: Record<StatusTone, ToneColors> = {
  running: { bg: '#E4EDFA', fg: '#1B4F9E', dot: '#1B5FC1' },
  completed: { bg: '#E3F2E8', fg: '#17663A', dot: '#1F8A4C' },
  neutral: { bg: '#EEF0F3', fg: '#4A5260', dot: '#8A93A1' },
  attention: { bg: '#FDF0D5', fg: '#7A4200', dot: '#C77700' },
  fault: { bg: '#FBE7E5', fg: '#A3261B', dot: '#C0392B' },
};

const darkTones: Record<StatusTone, ToneColors> = {
  running: { bg: '#16263D', fg: '#9CC3F5', dot: '#6FA8F5' },
  completed: { bg: '#14291D', fg: '#86D19E', dot: '#5CC98A' },
  neutral: { bg: '#232933', fg: '#C3CAD4', dot: '#7C8594' },
  attention: { bg: '#33260F', fg: '#F2C470', dot: '#F2B544' },
  fault: { bg: '#361817', fg: '#F4A097', dot: '#EF7B6E' },
};

export const fontSans = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif';
export const fontMono = '"IBM Plex Mono", Consolas, "Courier New", monospace';
/** Inset inside panels (theme spacing units): 16px everywhere. */
export const panelPadding = 2;
/** Panel and column headings: 11px uppercase labels, as in the approved mock. */
export const columnHeading = { fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', lineHeight: '16px', textTransform: 'uppercase', color: 'surface.label' } as const;

export function createAppTheme(mode: PaletteMode) {
  const dark = mode === 'dark';
  const primary = dark ? '#6FA8F5' : '#1B5FC1';
  const divider = dark ? '#2C333E' : '#D5DAE0';
  const surface: Surface = dark
    ? { head: '#1C212A', headLine: '#2A313C', rowLine: '#222831', track: '#25324A', label: '#AEB6C3', control: '#3A4350' }
    : { head: '#F6F7F9', headLine: '#DDE1E6', rowLine: '#EEF0F3', track: '#DCE5F3', label: '#4A5260', control: '#C9D0D9' };
  const focus = { outline: '2px solid', outlineColor: primary, outlineOffset: 2 };
  const touchMedia = '@media (pointer: coarse), (max-width: 600px)';
  const touch = { [touchMedia]: { minHeight: layout.touchRow, minWidth: layout.touchRow } };
  return createTheme({
    palette: {
      mode,
      primary: { main: primary, contrastText: dark ? '#0A1220' : '#FFFFFF' },
      secondary: { main: dark ? '#C3CAD4' : '#15191F' },
      success: { main: dark ? '#86D19E' : '#17663A' },
      warning: { main: dark ? '#F2B544' : '#A15C00', contrastText: dark ? '#1A1406' : '#FFFFFF' },
      error: { main: dark ? '#F4A097' : '#A3261B' },
      info: { main: primary },
      background: { default: dark ? '#0F1217' : '#ECEEF1', paper: dark ? '#171B22' : '#FFFFFF' },
      text: { primary: dark ? '#E6E9EE' : '#15191F', secondary: dark ? '#9CA5B3' : '#5A6372' },
      divider,
      rail: dark
        ? { bg: '#0A0C10', text: '#A0A9B7', activeBg: '#1E242E', activeText: '#FFFFFF', muted: '#7C8594' }
        : { bg: '#15181E', text: '#A9B1BE', activeBg: '#262B34', activeText: '#FFFFFF', muted: '#8C95A3' },
      tone: dark ? darkTones : lightTones,
      surface,
      attentionSurface: dark
        ? { line: '#7A5A1C', head: '#2A2112', text: '#F2C470', action: '#F2B544', actionText: '#1A1406' }
        : { line: '#E3B25A', head: '#FDF3DF', text: '#7A4200', action: '#A15C00', actionText: '#FFFFFF' },
    },
    shape: { borderRadius: layout.radius },
    typography: {
      fontFamily: fontSans,
      fontSize: 14,
      body1: { fontSize: 14, lineHeight: '20px' },
      body2: { fontSize: 13, lineHeight: '20px' },
      caption: { fontSize: 12, lineHeight: '16px' },
      overline: { fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', lineHeight: '16px' },
      h1: { fontSize: 24, fontWeight: 600, lineHeight: '32px' },
      h4: { fontWeight: 600 },
      h5: { fontSize: 20, fontWeight: 600, lineHeight: '28px' },
      h6: { fontSize: 16, fontWeight: 600, lineHeight: '24px' },
      button: { fontSize: 13, fontWeight: 600 },
    },
    components: {
      MuiCssBaseline: { styleOverrides: {
        ':root': { colorScheme: mode },
        body: { overflowWrap: 'break-word', fontSize: 14, lineHeight: '20px' },
        '*': { scrollbarColor: dark ? '#3A4350 #171B22' : '#A3ADBA #ECEEF1' },
        '*:focus-visible': focus,
        'code, kbd, pre, samp': { fontFamily: fontMono },
      } },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: { textTransform: 'none', minHeight: layout.control, padding: '0 16px', borderRadius: layout.radius, ...touch, '&:focus-visible': focus },
          sizeSmall: { minHeight: 32, padding: '0 8px' },
          outlined: { borderColor: surface.control },
        },
      },
      MuiIconButton: { styleOverrides: { root: { borderRadius: layout.radius, ...touch, '&:focus-visible': focus } } },
      // iOS Safari zooms the page into any field below 16px when it is focused.
      MuiInputBase: { styleOverrides: { root: { fontSize: 14, [touchMedia]: { minHeight: layout.touchRow, fontSize: 16 } } } },
      MuiOutlinedInput: { styleOverrides: { notchedOutline: { borderColor: surface.control } } },
      MuiMenuItem: { styleOverrides: { root: { fontSize: 14, minHeight: layout.row, ...touch } } },
      MuiTabs: { styleOverrides: { root: { minHeight: layout.header, [touchMedia]: { minHeight: layout.touchRow } } } },
      MuiTab: { styleOverrides: { root: { textTransform: 'none', minHeight: layout.header, fontSize: 14, padding: '0 12px', [touchMedia]: { minHeight: layout.touchRow } } } },
      MuiToggleButton: { styleOverrides: { root: { textTransform: 'none', fontSize: 13, height: 32, padding: '0 12px', borderColor: surface.control, [touchMedia]: { height: layout.touchRow } } } },
      MuiPaper: { styleOverrides: { root: { backgroundImage: 'none' }, outlined: { borderColor: divider }, rounded: { borderRadius: layout.radius } } },
      MuiCard: { defaultProps: { variant: 'outlined' }, styleOverrides: { root: { borderRadius: layout.radius } } },
      MuiCardContent: { styleOverrides: { root: { padding: layout.inset, '&:last-child': { paddingBottom: layout.inset } } } },
      MuiTableCell: { styleOverrides: {
        root: { fontSize: 13, height: layout.row, paddingTop: 0, paddingBottom: 0, borderColor: surface.rowLine },
        head: { backgroundColor: surface.head, color: surface.label, fontSize: 11, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', borderColor: surface.headLine },
      } },
      MuiAlert: { styleOverrides: { root: { borderRadius: layout.radius, fontSize: 13 } } },
      MuiDialog: { styleOverrides: { paper: { '&:not(.MuiDialog-paperFullScreen)': { '@media (max-width: 600px)': { margin: 8, maxWidth: 'calc(100% - 16px)' } } } } },
    },
  });
}

export default createAppTheme('light');
