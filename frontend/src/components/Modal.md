# Modal Focus Management

This document describes the modal focus management system implemented for PyRobot, providing comprehensive accessibility features for dialog components.

## Components

### 1. `useModalFocus` Hook

A React hook that provides complete focus management for modal dialogs.

**Features:**
- Focus trapping within modal boundaries
- Escape key handling for modal closure
- Proper focus restoration when modal closes
- Initial focus management
- Background content isolation (inert attribute)

**Usage:**

```typescript
import { useModalFocus } from '../hooks/useModalFocus';

const MyDialog = ({ open, onClose }) => {
  const { modalRef } = useModalFocus({
    isOpen: open,
    onClose: onClose,
    initialFocusSelector: 'input[type="text"]', // Optional: specific element to focus
    restoreFocus: true,        // Default: true
    trapFocus: true,          // Default: true
    closeOnEscape: true       // Default: true
  });

  return (
    <Dialog ref={modalRef} open={open} onClose={onClose}>
      {/* Dialog content */}
    </Dialog>
  );
};
```

### 2. `Modal` Component

A reusable, accessible modal wrapper around Material-UI Dialog.

**Features:**
- Built-in focus management
- Proper ARIA attributes
- Screen reader announcements
- Customizable focus behavior
- Close button options

**Usage:**

```typescript
import Modal from '../components/Modal';

const MyComponent = () => {
  const [open, setOpen] = useState(false);

  return (
    <Modal
      open={open}
      onClose={() => setOpen(false)}
      title="My Dialog"
      maxWidth="sm"
      fullWidth
      announceOnOpen="Dialog opened successfully"
      initialFocusSelector="button.primary"
    >
      {/* Modal content */}
      <p>Dialog content goes here</p>
    </Modal>
  );
};
```

## Implementation Guide

### For New Dialogs

1. **Use the Modal component** for simple dialogs:
```typescript
<Modal
  open={isOpen}
  onClose={handleClose}
  title="My Dialog"
  actions={
    <Button onClick={handleClose}>Close</Button>
  }
>
  <p>Content here</p>
</Modal>
```

2. **Use useModalFocus hook** for existing MUI Dialogs:
```typescript
const { modalRef } = useModalFocus({
  isOpen: open,
  onClose: handleClose,
  initialFocusSelector: 'input:first-of-type'
});

<Dialog ref={modalRef} open={open} onClose={handleClose}>
  {/* Existing dialog content */}
</Dialog>
```

### For Existing Dialogs

Update existing dialogs to use the focus management system:

1. **Import the hook:**
```typescript
import { useModalFocus } from '../hooks/useModalFocus';
```

2. **Add the hook:**
```typescript
const { modalRef } = useModalFocus({
  isOpen: open,
  onClose: handleClose
});
```

3. **Add ref to Dialog:**
```typescript
<Dialog ref={modalRef} open={open} onClose={handleClose}>
```

4. **Add proper ARIA attributes:**
```typescript
<Dialog
  ref={modalRef}
  open={open}
  onClose={handleClose}
  aria-labelledby="dialog-title"
  aria-describedby="dialog-description"
>
  <DialogTitle id="dialog-title">Title</DialogTitle>
  <DialogContent id="dialog-description">Content</DialogContent>
</Dialog>
```

## Accessibility Features

### Focus Management
- **Focus Trapping**: Tab navigation is constrained within the modal
- **Focus Restoration**: Focus returns to the triggering element when modal closes
- **Initial Focus**: Automatic focus on the first interactive element or custom selector

### Keyboard Support
- **Escape Key**: Closes the modal (can be disabled)
- **Tab/Shift+Tab**: Cycles through focusable elements within the modal
- **Enter/Space**: Activates focused buttons and controls

### Screen Reader Support
- **ARIA Labels**: Proper `aria-labelledby` and `aria-describedby` attributes
- **Role Attributes**: `role="dialog"` and `aria-modal="true"`
- **Live Announcements**: Optional announcements when modals open
- **Inert Background**: Background content is hidden from screen readers

## Examples

### Simple Confirmation Dialog
```typescript
import Modal from '../components/Modal';

const ConfirmDialog = ({ open, onClose, onConfirm, message }) => (
  <Modal
    open={open}
    onClose={onClose}
    title="Confirm Action"
    maxWidth="xs"
    actions={
      <>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={onConfirm} variant="contained" color="primary">
          Confirm
        </Button>
      </>
    }
  >
    <Typography>{message}</Typography>
  </Modal>
);
```

### Form Dialog with Custom Focus
```typescript
import { useModalFocus } from '../hooks/useModalFocus';

const FormDialog = ({ open, onClose }) => {
  const { modalRef } = useModalFocus({
    isOpen: open,
    onClose,
    initialFocusSelector: 'input[name="name"]'
  });

  return (
    <Dialog ref={modalRef} open={open} onClose={onClose}>
      <DialogTitle>User Information</DialogTitle>
      <DialogContent>
        <TextField name="name" label="Name" />
        <TextField name="email" label="Email" />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button type="submit">Save</Button>
      </DialogActions>
    </Dialog>
  );
};
```

## Best Practices

1. **Always use proper ARIA attributes** for dialog titles and descriptions
2. **Set initial focus** to the most logical first element (usually the first input or primary button)
3. **Don't close on escape** during loading states or unsaved changes
4. **Provide screen reader announcements** for important state changes
5. **Test with keyboard only** to ensure all functionality is accessible
6. **Test with screen readers** to verify proper announcements and navigation

## Browser Support

The focus management system is compatible with:
- Chrome 88+
- Firefox 85+
- Safari 14+
- Edge 88+

The `inert` attribute is polyfilled for older browsers that don't support it natively.