import { useEffect, useState } from 'react';
import { NavigateFunction, useNavigate } from 'react-router-dom';

export interface Shortcut {
  key: string;
  ctrl?: boolean;
  alt?: boolean;
  shift?: boolean;
  description: string;
}

interface BoundShortcut extends Shortcut {
  run: (navigate: NavigateFunction) => void;
}

// Alt+1 … Alt+9 in this order.
const PAGES: Array<[path: string, name: string]> = [
  ['/', 'Dashboard'],
  ['/database', 'Database'],
  ['/camera', 'Camera'],
  ['/labware', 'Labware'],
  ['/maintenance', 'Maintenance'],
  ['/system-status', 'System Status'],
  ['/scheduling', 'Scheduling'],
  ['/about', 'About'],
  ['/logfile', 'LogFile'],
];

const focusSearch = () => {
  const target = document.querySelector<HTMLInputElement>('input[type="search"], input[placeholder*="search" i]')
    ?? document.querySelector<HTMLInputElement>('input:not([type="hidden"])');
  target?.focus();
  target?.select();
};

const SHORTCUTS: BoundShortcut[] = [
  ...PAGES.map(([path, name], index): BoundShortcut => ({
    key: String(index + 1), alt: true, description: `Go to ${name}`, run: navigate => navigate(path),
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
export const useKeyboardNavigation = ({ enabled = true }: { enabled?: boolean } = {}) => {
  const navigate = useNavigate();
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    if (!enabled) return;
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
      if (shortcut) {
        event.preventDefault();
        event.stopPropagation();
        shortcut.run(navigate);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [enabled, navigate]);

  return { helpOpen, closeHelp: () => setHelpOpen(false) };
};
