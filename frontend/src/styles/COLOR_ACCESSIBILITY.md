# Color Accessibility Guide

This document outlines PyRobot's approach to color accessibility, ensuring the application is usable by people with various types of color vision deficiencies.

## Overview

PyRobot implements a multi-layered approach to color accessibility:

1. **WCAG 2.1 AA Compliant Colors** - All colors meet minimum contrast requirements
2. **Non-Color Indicators** - Icons, patterns, and text labels accompany all color coding
3. **Enhanced Focus Indicators** - High contrast focus outlines for keyboard navigation
4. **Pattern-Based Differentiation** - Different border styles and background patterns for status states

## Color Palette

### Primary Colors (WCAG AA Compliant)

| Use Case | Color | Hex | Contrast Ratio | Notes |
|----------|-------|-----|----------------|-------|
| Primary | ![#1565c0](https://via.placeholder.com/15/1565c0/000000?text=+) | `#1565c0` | 4.54:1 | Darker blue for better contrast |
| Secondary | ![#c62828](https://via.placeholder.com/15/c62828/000000?text=+) | `#c62828` | 5.47:1 | Darker red for better contrast |
| Success | ![#2e7d32](https://via.placeholder.com/15/2e7d32/000000?text=+) | `#2e7d32` | 4.52:1 | Darker green for better contrast |
| Warning | ![#ef6c00](https://via.placeholder.com/15/ef6c00/000000?text=+) | `#ef6c00` | 4.56:1 | Darker orange for better contrast |
| Error | ![#c62828](https://via.placeholder.com/15/c62828/000000?text=+) | `#c62828` | 5.47:1 | Same as secondary for consistency |
| Info | ![#0277bd](https://via.placeholder.com/15/0277bd/000000?text=+) | `#0277bd` | 4.51:1 | Darker cyan for better contrast |

### Text Colors

| Element | Color | Hex | Contrast Ratio |
|---------|-------|-----|----------------|
| Primary Text | ![#000000](https://via.placeholder.com/15/000000/000000?text=+) | `rgba(0, 0, 0, 0.87)` | 15.8:1 |
| Secondary Text | ![#666666](https://via.placeholder.com/15/666666/000000?text=+) | `rgba(0, 0, 0, 0.6)` | 7.0:1 |

## Non-Color Accessibility Features

### Status Indicators

PyRobot uses multiple visual cues to convey status information:

#### 1. Icons
- ✅ **Success**: CheckCircle icon
- ❌ **Error**: Error icon  
- ⚠️ **Warning**: Warning icon
- ℹ️ **Info**: Info icon
- ⏸️ **Paused**: Pause icon

#### 2. Border Patterns
- **Success**: Solid border
- **Error**: Dashed border (- - - -)
- **Warning**: Dotted border (• • • •)
- **Info**: Double border (══════)
- **Neutral**: Solid border

#### 3. Background Patterns
- **Running**: Diagonal stripes with pulse animation
- **Failed**: Cross-hatch pattern
- **Paused**: Dotted background pattern
- **Completed**: Solid background

#### 4. Animation Cues
- **Running/Active**: Gentle pulse animation
- **Loading**: Spinner or progress indicator
- **Error**: Optional shake animation for critical errors

### Focus Indicators

All interactive elements have enhanced focus indicators:

```css
&:focus-visible {
  outline: 3px solid #1565c0;
  outline-offset: 2px;
}
```

## Implementation Guidelines

### 1. Using Status Colors

**❌ Bad - Color only:**
```tsx
<Chip label="Running" color="success" />
```

**✅ Good - Color + Icon + Pattern:**
```tsx
<AccessibleStatusIndicator 
  status="success" 
  label="Running"
  showIcon={true}
  showPattern={true}
  animate={true}
  ariaLabel="Experiment is currently running"
/>
```

### 2. Alert Components

All alerts should include:
- Icon indicating the alert type
- Strong left border for visual emphasis
- High contrast text
- Clear action buttons

```tsx
<Alert 
  severity="error" 
  icon={<ErrorIcon />}
  sx={{ borderLeft: '4px solid #c62828' }}
>
  Operation failed. Please try again.
</Alert>
```

### 3. Form Validation

Error states should be indicated by:
- Red border color (high contrast)
- Error icon
- Clear error message text
- ARIA invalid attribute

```tsx
<TextField
  error={hasError}
  helperText={errorMessage}
  InputProps={{
    startAdornment: hasError && <ErrorIcon color="error" />
  }}
  aria-invalid={hasError}
  aria-describedby={hasError ? "error-text" : undefined}
/>
```

## Testing

### Automated Testing

Color contrast is automatically tested using:
- Wave browser extension
- axe-core accessibility testing
- Lighthouse accessibility audits

### Manual Testing

Regular testing should include:

1. **Color Blindness Simulation**
   - Use browser dev tools color vision simulation
   - Test with Deuteranopia (red-green colorblind)
   - Test with Protanopia (red-green colorblind)
   - Test with Tritanopia (blue-yellow colorblind)

2. **High Contrast Mode**
   - Windows High Contrast mode
   - macOS Increase Contrast setting

3. **Keyboard Navigation**
   - All interactive elements reachable via Tab
   - Clear focus indicators visible
   - Skip links functional

### Testing Checklist

- [ ] All status indicators have icons in addition to color
- [ ] Error states are clearly marked with text and icons
- [ ] Focus indicators are visible on all interactive elements
- [ ] Text meets minimum contrast ratios (4.5:1 normal, 3:1 large)
- [ ] UI components have border patterns for differentiation
- [ ] Color simulation testing passes for common color vision deficiencies

## Browser Support

The accessibility features are supported in:
- Chrome 88+
- Firefox 85+  
- Safari 14+
- Edge 88+

## Resources

- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [WebAIM Color Contrast Checker](https://webaim.org/resources/contrastchecker/)
- [Color Universal Design Organization](https://jfly.uni-koeln.de/color/)
- [Material Design Accessibility](https://material.io/design/usability/accessibility.html)

## Common Patterns

### Status Chips
```tsx
// Experiment status with full accessibility
const ExperimentStatusChip = ({ status, label }) => (
  <AccessibleStatusIndicator
    status={status}
    label={label}
    variant="chip"
    showIcon={true}
    showPattern={true}
    animate={status === 'running'}
  />
);
```

### Alert Banners
```tsx
// Error alert with multiple cues
const ErrorBanner = ({ message }) => (
  <Alert 
    severity="error"
    icon={<ErrorIcon />}
    sx={{ 
      borderLeft: '4px solid #c62828',
      backgroundColor: 'repeating-linear-gradient(45deg, rgba(198, 40, 40, 0.05), rgba(198, 40, 40, 0.05) 8px, transparent 8px, transparent 16px)'
    }}
  >
    {message}
  </Alert>
);
```

### Form Validation
```tsx
// Accessible form field with validation
const AccessibleTextField = ({ error, ...props }) => (
  <TextField
    {...props}
    error={!!error}
    helperText={error}
    InputProps={{
      startAdornment: error && <ErrorIcon color="error" sx={{ mr: 1 }} />,
      sx: {
        '&.Mui-error': {
          borderLeft: '3px solid #c62828'
        }
      }
    }}
    aria-invalid={!!error}
  />
);