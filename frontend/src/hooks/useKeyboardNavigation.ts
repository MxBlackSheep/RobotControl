import { useEffect, useState } from 'react';
import { NavigateFunction, useNavigate } from 'react-router-dom';
import { canOpen, navigationItems, type NavigationUser } from '../components/navigation';

export interface Shortcut {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  description: string;
}

interface BoundShortcut extends Shortcut {
  run: (navigate: NavigateFunction) => void;
  /** The page it opens; a role that may not open it gets no shortcut. */
  path?: string;
}

// Alt+1 … Alt+9 in this order; names are the menu's. About is not in the menu.
const PAGES = ['/', '/database', '/camera', '/labware', '/maintenance', '/system-status', '/scheduling', '/about', '/logfile'];
const pageName = (path: string) => navigationItems.find(item => item.path === path)?.label ?? 'About';

const focusSearch = () => {
  const target = document.querySelector<HTMLInputElement>('input[type="search"], input[placeholder*="search" i]')
    ?? document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
  target?.focus();
  target?.select();
};

const SHORTCUTS: BoundShortcut[] = [
  ...PAGES.map((path, index): BoundShortcut => ({
    key: String(index + 1), alt: true, description: `Go to ${pageName(path)}`, run: navigate => navigate(path), path,
  })),
  { key: 'h', ctrl: true, description: 'Go to Home/Dashboard', run: navigate => navigate('/') },
  { key: 'b', ctrl: true, description: 'Go Back', run: () => window.history.back() },
  { key: 'r', ctrl: true, shift: true, description: 'Refresh Page', run: () => window.location.reload() },
  { key: '/', description: 'Focus Search/First Input', run: focusSearch },
  { key: 'Escape', description: 'Close Dialog/Clear Focus', run: () => (document.activeElement as HTMLElement | null)?.blur?.() },
];

/** Everything shown in the shortcuts help dialog. */
export const SHORTCUT_HELP: Shortcut[] = [
  ...SHORTCUTS,
  { key: '?', description: 'Show Keyboard Shortcuts (this dialog)' },
];

const isTyping = (element: Element | null) =>
  element instanceof HTMLElement && (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA' || element.isContentEditable);

/** Global navigation shortcuts; `?` opens the help dialog the caller renders. */
export const useKeyboardNavigation = (user: NavigationUser) => {
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);

  const role = user?.role;
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      // MUI owns modal/menu keys and focus restoration. Never navigate away from a draft.
      if (document.querySelector('.MuiModal-root:not([aria-hidden="true"])')) return;
      const typing = isTyping(document.activeElement);

      if (event.key === '?' && !event.ctrlKey && !event.altKey && !typing) {
        event.preventDefault();
        setHelpOpen(true);
        return;
      }
      if (typing && event.key !== 'Escape') return;

      const shortcut = SHORTCUTS.find(s =>
        s.key.toLowerCase() === event.key.toLowerCase()
        && Boolean(s.ctrl) === event.ctrlKey
        && Boolean(s.alt) === event.altKey
        && Boolean(s.shift) === event.shiftKey);
      if (shortcut && (!shortcut.path || canOpen(shortcut.path, { role }))) {
        event.preventDefault();
        event.stopPropagation();
        shortcut.run(navigate);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [role, navigate]);

  return { helpOpen, closeHelp: () => setHelpOpen(false) };
};
