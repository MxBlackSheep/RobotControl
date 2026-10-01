import { Component, ErrorInfo, ReactNode } from 'react';
import Alert from '@mui/material/Alert';
import Button from '@mui/material/Button';

/**
 * Keeps the shell (navigation, status bar) usable when a page fails to load or render,
 * typically a page chunk that could not be fetched over a dropped connection.
 * App keys it by route, so navigating elsewhere clears the error.
 */
export default class PageLoadBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page failed to load:', error, info);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return <Alert severity="error" action={<Button color="inherit" onClick={() => window.location.reload()}>Reload</Button>}>
      This page could not load. Check the connection, then reload.
    </Alert>;
  }
}
