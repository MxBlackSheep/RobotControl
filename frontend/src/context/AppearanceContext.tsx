import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { CssBaseline, IconButton, Menu, MenuItem, ThemeProvider, Tooltip, useMediaQuery } from '@mui/material';
import ContrastIcon from '@mui/icons-material/Contrast';
import { Toaster } from 'react-hot-toast';
import { createAppTheme } from '../theme';

type Appearance = 'system' | 'light' | 'dark';
const storageKey = 'robotcontrol-appearance';
const AppearanceContext = createContext<{ preference: Appearance; setPreference: (value: Appearance) => void }>({ preference: 'system', setPreference: () => {} });
const readPreference = (): Appearance => {
  try { const value = localStorage.getItem(storageKey); return value === 'light' || value === 'dark' ? value : 'system'; }
  catch { return 'system'; }
};

export function AppearanceProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreference] = useState<Appearance>(readPreference);
  const systemDark = useMediaQuery('(prefers-color-scheme: dark)', { noSsr: true });
  const mode = preference === 'system' ? (systemDark ? 'dark' : 'light') : preference;
  const theme = useMemo(() => createAppTheme(mode), [mode]);
  useEffect(() => {
    document.documentElement.dataset.appearance = mode;
    document.documentElement.style.colorScheme = mode;
    document.documentElement.style.backgroundColor = theme.palette.background.default;
    try { localStorage.setItem(storageKey, preference); } catch { /* The theme still works when storage is unavailable. */ }
  }, [mode, preference, theme]);
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === storageKey) setPreference(readPreference()); };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  return <AppearanceContext.Provider value={{ preference, setPreference }}><ThemeProvider theme={theme}>
    <CssBaseline />{children}
    <Toaster position="top-right" toastOptions={{ style: { background: theme.palette.background.paper, color: theme.palette.text.primary } }} />
  </ThemeProvider></AppearanceContext.Provider>;
}

export function AppearanceControl() {
  const { preference, setPreference } = useContext(AppearanceContext);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  return <>
    <Tooltip title="Appearance"><IconButton aria-label="Appearance" aria-haspopup="menu" aria-expanded={!!anchor} onClick={event => setAnchor(event.currentTarget)}><ContrastIcon /></IconButton></Tooltip>
    <Menu anchorEl={anchor} open={!!anchor} onClose={() => setAnchor(null)}>
      {(['system', 'light', 'dark'] as const).map(value => <MenuItem key={value} role="menuitemradio" aria-checked={preference === value} selected={preference === value} onClick={() => { setPreference(value); setAnchor(null); }}>{value[0].toUpperCase() + value.slice(1)}</MenuItem>)}
    </Menu>
  </>;
}
