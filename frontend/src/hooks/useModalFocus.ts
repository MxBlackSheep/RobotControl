/**
 * Modal Focus Management Hook for RobotControl
 *
 * Handles focus trapping and focus restoration for dialogs while allowing
 * MUI to manage body scroll locking. Previously the hook forced
 * document.body overflow to hidden which left the page unscrollable after
 * the dialog closed.
 */

import { useEffect, useRef, useCallback } from 'react';

interface UseModalFocusOptions {
  isOpen: boolean;
  onClose: () => void;
  initialFocusSelector?: string;
  restoreFocus?: boolean;
  trapFocus?: boolean;
  closeOnEscape?: boolean;
}

export const useModalFocus = ({
  isOpen,
  onClose,
  initialFocusSelector,
  restoreFocus = true,
  trapFocus = true,
  closeOnEscape = true
}: UseModalFocusOptions) => {
  const previousActiveElement = useRef<HTMLElement | null>(null);
  const modalRef = useRef<HTMLDivElement>(null);

  const focusableSelectors = [
    'button:not([disabled])',
    '[href]:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"]):not([disabled])',
    'details:not([disabled])',
    'summary:not(:disabled)'
  ].join(', ');

  const getFocusableElements = useCallback((): HTMLElement[] => {
    if (!modalRef.current) {
      return [];
    }

    const elements = Array.from(
      modalRef.current.querySelectorAll(focusableSelectors)
    ) as HTMLElement[];

    return elements.filter(element => {
      const style = window.getComputedStyle(element);
      return (
        style.display !== 'none' &&
        style.visibility !== 'hidden' &&
        !element.hasAttribute('inert')
      );
    });
  }, [focusableSelectors]);

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (!modalRef.current || !isOpen) {
      return;
    }

    if (closeOnEscape && event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }

    if (trapFocus && event.key === 'Tab') {
      const focusableEls = getFocusableElements();
      if (focusableEls.length === 0) {
        event.preventDefault();
        return;
      }

      const firstFocusable = focusableEls[0];
      const lastFocusable = focusableEls[focusableEls.length - 1];

      if (event.shiftKey) {
        if (document.activeElement === firstFocusable) {
          event.preventDefault();
          lastFocusable.focus();
        }
      } else if (document.activeElement === lastFocusable) {
        event.preventDefault();
        firstFocusable.focus();
      }
    }
  }, [closeOnEscape, getFocusableElements, isOpen, onClose, trapFocus]);

  const setInitialFocus = useCallback(() => {
    if (!modalRef.current || !isOpen) {
      return;
    }

    window.setTimeout(() => {
      let elementToFocus: HTMLElement | null = null;

      if (initialFocusSelector) {
        elementToFocus = modalRef.current!.querySelector(initialFocusSelector);
      }

      if (!elementToFocus) {
        const focusableEls = getFocusableElements();
        elementToFocus = focusableEls[0] || modalRef.current;
      }

      elementToFocus?.focus();
    }, 50);
  }, [getFocusableElements, initialFocusSelector, isOpen]);

  useEffect(() => {
    if (!isOpen || typeof document === 'undefined') {
      return;
    }

    previousActiveElement.current = document.activeElement as HTMLElement;
    setInitialFocus();
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown, isOpen, setInitialFocus]);

  useEffect(() => {
    if (!isOpen && restoreFocus && previousActiveElement.current) {
      window.setTimeout(() => {
        try {
          previousActiveElement.current?.focus();
        } catch {
          document.body.focus();
        }
      }, 50);
    }
  }, [isOpen, restoreFocus]);

  return {
    modalRef,
    setInitialFocus
  };
};

export default useModalFocus;
