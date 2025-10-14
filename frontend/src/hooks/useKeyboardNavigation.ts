/**
 * Keyboard Navigation Hook for RobotControl
 * 
 * Provides keyboard shortcuts and navigation support for better accessibility
 * and power user experience.
 */

import { useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

interface KeyboardShortcut {
  key: string;
  ctrlKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
  action: () => void;
  description: string;
}

interface UseKeyboardNavigationProps {
  shortcuts?: KeyboardShortcut[];
  enabled?: boolean;
}

export const useKeyboardNavigation = ({ 
  shortcuts = [], 
  enabled = true 
}: UseKeyboardNavigationProps = {}) => {
  const navigate = useNavigate();
  const location = useLocation();

  // Global navigation shortcuts
  const globalShortcuts: KeyboardShortcut[] = [
    {
      key: '1',
      altKey: true,
      action: () => navigate('/'),
      description: 'Go to Dashboard (Alt+1)'
    },
    {
      key: '2',
      altKey: true,
      action: () => navigate('/database'),
      description: 'Go to Database (Alt+2)'
    },
    {
      key: '3',
      altKey: true,
      action: () => navigate('/camera'),
      description: 'Go to Camera (Alt+3)'
    },
    {
      key: '4',
      altKey: true,
      action: () => navigate('/system-status'),
      description: 'Go to System Status (Alt+4)'
    },
    {
      key: '5',
      altKey: true,
      action: () => navigate('/scheduling'),
      description: 'Go to Scheduling (Alt+5)'
    },
    {
      key: '6',
      altKey: true,
      action: () => navigate('/about'),
      description: 'Go to About (Alt+6)'
    },
    {
      key: 'h',
      ctrlKey: true,
      action: () => navigate('/'),
      description: 'Go to Home/Dashboard (Ctrl+H)'
    },
    {
      key: 'b',
      ctrlKey: true,
      action: () => window.history.back(),
      description: 'Go Back (Ctrl+B)'
    },
    {
      key: 'r',
      ctrlKey: true,
      shiftKey: true,
      action: () => window.location.reload(),
      description: 'Refresh Page (Ctrl+Shift+R)'
    },
    {
      key: '/',
      action: () => {
        // Focus first search input or main content
        const searchInput = document.querySelector('input[type="search"], input[placeholder*="search" i]') as HTMLInputElement;
        const firstInput = document.querySelector('input:not([type="hidden"])') as HTMLInputElement;
        const target = searchInput || firstInput;
        if (target) {
          target.focus();
          target.select();
        }
      },
      description: 'Focus Search/First Input (/)'
    },
    {
      key: 'Escape',
      action: () => {
        // Close any open dialogs, modals, or clear focus
        const activeElement = document.activeElement as HTMLElement;
        if (activeElement && activeElement.blur) {
          activeElement.blur();
        }
        
        // Try to close any open dialogs
        const closeButtons = document.querySelectorAll('[aria-label*="close" i], [title*="close" i], .MuiDialog-root .MuiIconButton-root');
        if (closeButtons.length > 0) {
          (closeButtons[0] as HTMLElement).click();
        }
      },
      description: 'Escape/Close (Esc)'
    }
  ];

  // Combine global and local shortcuts
  const allShortcuts = [...globalShortcuts, ...shortcuts];

  // Keyboard event handler
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (!enabled) return;

    // Don't trigger shortcuts when user is typing in inputs
    const activeElement = document.activeElement;
    const isInputField = activeElement && (
      activeElement.tagName === 'INPUT' ||
      activeElement.tagName === 'TEXTAREA' ||
      (activeElement as HTMLElement).contentEditable === 'true'
    );

    // Allow Escape key even in input fields
    if (isInputField && event.key !== 'Escape') {
      return;
    }

    // Find matching shortcut
    const matchingShortcut = allShortcuts.find(shortcut => {
      return shortcut.key.toLowerCase() === event.key.toLowerCase() &&
             (shortcut.ctrlKey || false) === event.ctrlKey &&
             (shortcut.altKey || false) === event.altKey &&
             (shortcut.shiftKey || false) === event.shiftKey;
    });

    if (matchingShortcut) {
      event.preventDefault();
      event.stopPropagation();
      matchingShortcut.action();
    }
  }, [allShortcuts, enabled]);

  // Tab order management
  const manageFocusOrder = useCallback(() => {
    // Ensure proper tab order for the current page
    const focusableElements = document.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    focusableElements.forEach((element, index) => {
      const htmlElement = element as HTMLElement;
      // Only set tabindex if not already set
      if (!htmlElement.hasAttribute('tabindex')) {
        htmlElement.tabIndex = 0;
      }
    });
  }, []);

  // Focus trap for modals/dialogs
  const createFocusTrap = useCallback((container: HTMLElement) => {
    const focusableElements = container.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    if (focusableElements.length === 0) return () => {};

    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;

    const handleTabKeyPress = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;

      if (event.shiftKey) {
        if (document.activeElement === firstElement) {
          event.preventDefault();
          lastElement.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          event.preventDefault();
          firstElement.focus();
        }
      }
    };

    container.addEventListener('keydown', handleTabKeyPress);
    
    // Focus first element
    firstElement.focus();

    // Return cleanup function
    return () => {
      container.removeEventListener('keydown', handleTabKeyPress);
    };
  }, []);

  // Skip to main content
  const skipToMainContent = useCallback(() => {
    const mainContent = document.querySelector('main, [role="main"], #main-content') as HTMLElement;
    if (mainContent) {
      mainContent.focus();
      mainContent.scrollIntoView();
    }
  }, []);

  // Setup keyboard listeners
  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    manageFocusOrder();

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown, manageFocusOrder]);

  // Re-manage focus order on route change
  useEffect(() => {
    // Small delay to ensure DOM is updated
    const timeout = setTimeout(manageFocusOrder, 100);
    return () => clearTimeout(timeout);
  }, [location.pathname, manageFocusOrder]);

  return {
    shortcuts: allShortcuts,
    manageFocusOrder,
    createFocusTrap,
    skipToMainContent
  };
};

export default useKeyboardNavigation;
