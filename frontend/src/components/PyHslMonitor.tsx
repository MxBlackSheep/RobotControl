import { useEffect, useRef, useState } from 'react';
import { Box, Typography, useTheme } from '@mui/material';
import { api } from '../services/api';
import { appErrorMessage } from '../services/requestError';
import { layout } from '../theme';

export type MonitorView = { deck: unknown; state: unknown };

/**
 * PyHSL's own read-only Run view (status, deck, transport and current step), mounted in a frame with scripts
 * only: no same origin, so PyHSL's code cannot reach RobotControl's sign-in tokens. Both bodies go in unchanged
 * by postMessage; PyHSL owns the drawing and shows "Run view not shown" itself when it cannot read them.
 */
export default function PyHslMonitor({ view, error }: { view: MonitorView | null; error: string | null }) {
  const theme = useTheme().palette.mode;
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  const [script, setScript] = useState<string | null>(null);
  const [scriptError, setScriptError] = useState<string | null>(null);

  const loading = useRef(false);
  // Read once; after a failure, again with each new reading, so the view returns when Run Control does.
  useEffect(() => {
    if (script || loading.current) return;
    loading.current = true;
    api.get('/api/pyhsl/monitor.js', { responseType: 'text' })
      .then(({ data }) => { setScript(data); setScriptError(null); },
        (err: any) => setScriptError(appErrorMessage(err) || 'the view could not be loaded'))
      .finally(() => { loading.current = false; });
  }, [script, view]);

  useEffect(() => {
    const listen = (event: MessageEvent) => { if (event.source === frame.current?.contentWindow && event.data === 'ready') setReady(true); };
    window.addEventListener('message', listen);
    return () => window.removeEventListener('message', listen);
  }, []);

  useEffect(() => {
    if (ready && view) frame.current?.contentWindow?.postMessage({ ...view, theme }, '*');
  }, [ready, view, theme]);

  const reason = scriptError || error;
  // Same size as the view, so a failure does not make the page jump.
  if (reason || !script) return <Box sx={{ height: '100%', p: 3, display: 'grid', placeItems: 'center', textAlign: 'center',
    border: 1, borderColor: 'divider', borderRadius: `${layout.radius}px`, bgcolor: 'background.paper' }}>
    <Typography role={reason ? 'alert' : undefined} sx={{ fontSize: 18, fontWeight: 500, color: reason ? 'text.primary' : 'text.secondary', overflowWrap: 'anywhere' }}>
      {reason ? `Run view not shown: ${reason}` : 'Loading'}
    </Typography>
  </Box>;
  return <Box component="iframe" ref={frame} title="Run view" sandbox="allow-scripts" srcDoc={frameDocument(script)}
    sx={{ display: 'block', width: '100%', height: '100%', border: 0 }} />;
}

// The script is inlined because a frame without an origin cannot send RobotControl's sign-in header.
const frameDocument = (script: string) => `<!doctype html><meta charset="utf-8">
<style>html,body,#view{margin:0;height:100%;background:transparent}</style><div id="view"></div>
<script>${script.replace(/<\/script/gi, '<\\/script')}</script>
<script>
addEventListener('message', event => {
  if (event.source !== parent) return;
  const element = document.getElementById('view');
  // A frame whose scheme differs from the page is drawn on an opaque white canvas.
  document.documentElement.style.colorScheme = event.data.theme;
  try {
    if (typeof PyHSLMonitor === 'undefined') throw new Error('the view did not load');
    element.removeAttribute('style');
    PyHSLMonitor.mount(element, event.data);
  } catch (error) {
    element.style.cssText = 'display:grid;place-items:center;text-align:center;font:500 18px system-ui,sans-serif';
    element.textContent = 'Run view not shown: ' + (error && error.message || error);
  }
});
parent.postMessage('ready', '*');
</script>`;
