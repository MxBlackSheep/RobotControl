/**
 * Accessible Modal Component for PyRobot
 * 
 * A wrapper around Material-UI Dialog that provides comprehensive accessibility features:
 * - Focus management and trapping
 * - Escape key handling
 * - Proper ARIA attributes
 * - Screen reader announcements
 * - Focus restoration on close
 */

import React, { forwardRef, useImperativeHandle } from 'react';
import {
  Dialog,
  DialogProps,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Typography,
  Box
} from '@mui/material';
import { Close as CloseIcon } from '@mui/icons-material';
import { useModalFocus } from '../hooks/useModalFocus';

export interface ModalProps extends Omit<DialogProps, 'ref'> {
  // Core modal props
  open: boolean;
  onClose: () => void;
  title?: string;
  closeButton?: boolean;
  
  // Focus management options
  initialFocusSelector?: string;
  restoreFocus?: boolean;
  trapFocus?: boolean;
  closeOnEscape?: boolean;
  
  // Accessibility props
  ariaLabel?: string;
  ariaDescribedBy?: string;
  announceOnOpen?: string;
  
  // Content slots
  children?: React.ReactNode;
  actions?: React.ReactNode;
  
  // Styling
  maxWidth?: DialogProps['maxWidth'];
  fullWidth?: boolean;
  fullScreen?: boolean;
}

export interface ModalRef {
  focus: () => void;
  close: () => void;
}

const Modal = forwardRef<ModalRef, ModalProps>(({
  // Core props
  open,
  onClose,
  title,
  closeButton = true,
  
  // Focus management
  initialFocusSelector,
  restoreFocus = true,
  trapFocus = true,
  closeOnEscape = true,
  
  // Accessibility
  ariaLabel,
  ariaDescribedBy,
  announceOnOpen,
  
  // Content
  children,
  actions,
  
  // Styling
  maxWidth = 'sm',
  fullWidth = false,
  fullScreen = false,
  
  // Other Dialog props
  ...dialogProps
}, ref) => {
  
  // Use our custom focus management hook
  const { modalRef, setInitialFocus } = useModalFocus({
    isOpen: open,
    onClose,
    initialFocusSelector,
    restoreFocus,
    trapFocus,
    closeOnEscape
  });

  // Expose methods to parent components
  useImperativeHandle(ref, () => ({
    focus: setInitialFocus,
    close: onClose
  }), [setInitialFocus, onClose]);

  // Screen reader announcement when modal opens
  React.useEffect(() => {
    if (open && announceOnOpen) {
      // Create temporary element for screen reader announcement
      const announcement = document.createElement('div');
      announcement.setAttribute('aria-live', 'polite');
      announcement.setAttribute('aria-atomic', 'true');
      announcement.style.position = 'absolute';
      announcement.style.left = '-10000px';
      announcement.style.top = 'auto';
      announcement.style.width = '1px';
      announcement.style.height = '1px';
      announcement.style.overflow = 'hidden';
      
      document.body.appendChild(announcement);
      
      // Add the announcement text
      setTimeout(() => {
        announcement.textContent = announceOnOpen;
      }, 100);
      
      // Clean up after announcement
      setTimeout(() => {
        if (document.body.contains(announcement)) {
          document.body.removeChild(announcement);
        }
      }, 1000);
    }
  }, [open, announceOnOpen]);

  return (
    <Dialog
      ref={modalRef}
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth={fullWidth}
      fullScreen={fullScreen}
      aria-labelledby={title ? 'modal-title' : undefined}
      aria-label={!title ? ariaLabel : undefined}
      aria-describedby={ariaDescribedBy}
      role="dialog"
      aria-modal="true"
      keepMounted={false} // Ensure proper cleanup
      disableRestoreFocus // We handle this ourselves
      disableAutoFocus // We handle this ourselves
      {...dialogProps}
    >
      {/* Title with optional close button */}
      {title && (
        <DialogTitle 
          id="modal-title"
          sx={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            pr: closeButton ? 1 : 3
          }}
        >
          <Typography variant="h6" component="h2">
            {title}
          </Typography>
          {closeButton && (
            <IconButton
              aria-label="Close dialog"
              onClick={onClose}
              sx={{ ml: 1 }}
            >
              <CloseIcon />
            </IconButton>
          )}
        </DialogTitle>
      )}

      {/* Main content */}
      {children && (
        <DialogContent
          dividers={Boolean(title || actions)}
          id={ariaDescribedBy}
        >
          {children}
        </DialogContent>
      )}

      {/* Action buttons */}
      {actions && (
        <DialogActions sx={{ px: 3, py: 2 }}>
          {actions}
        </DialogActions>
      )}

      {/* Close button for title-less modals */}
      {!title && closeButton && (
        <Box sx={{ position: 'absolute', top: 8, right: 8 }}>
          <IconButton
            aria-label="Close dialog"
            onClick={onClose}
          >
            <CloseIcon />
          </IconButton>
        </Box>
      )}
    </Dialog>
  );
});

Modal.displayName = 'Modal';

export default Modal;