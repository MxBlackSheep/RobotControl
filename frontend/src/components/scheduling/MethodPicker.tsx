import { useMemo, useState } from 'react';
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, List, ListItemButton, ListItemText, Radio, Typography } from '@mui/material';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import MethodExplorer from './MethodExplorer';
import { pathParts } from './methodFolders';

export default function MethodPicker({ methods, value, label, onChange, disabled }: {
  methods: { path: string; name: string }[]; value: string; label: string; onChange: (path: string) => void; disabled?: boolean;
}) {
  const fullScreen = useMediaQuery(useTheme().breakpoints.down('md'));
  const [open, setOpen] = useState(false);
  const [choice, setChoice] = useState(value);
  const items = useMemo(() => methods.filter(method => pathParts(method.path)).map(method => ({ ...method, id: method.path })).sort((a, b) => a.name.localeCompare(b.name) || a.path.localeCompare(b.path)), [methods]);
  return <>
    <Button variant="outlined" disabled={disabled} onClick={() => { setChoice(value); setOpen(true); }} aria-label={label} aria-haspopup="dialog">{label}</Button>
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="lg" fullWidth fullScreen={fullScreen} aria-labelledby="method-picker-title">
      <DialogTitle id="method-picker-title">{label}</DialogTitle>
      <DialogContent dividers sx={{ minHeight: '45vh' }}>{open && <MethodExplorer items={items} initialPath={value}>
        {(rows, relativePath) => <List aria-label="Methods in folder">{rows.map(method => <ListItemButton key={method.id} selected={choice === method.path}
          onClick={() => setChoice(method.path)} role="radio" aria-checked={choice === method.path}>
          <Radio checked={choice === method.path} tabIndex={-1} inputProps={{ 'aria-hidden': true }} />
          <ListItemText primary={method.name} secondary={relativePath(method.path)} sx={{ overflowWrap: 'anywhere' }} />
        </ListItemButton>)}</List>}
      </MethodExplorer>}</DialogContent>
      <DialogActions sx={{ flexWrap: 'wrap' }}><Typography variant="caption" sx={{ flex: 1, px: 1, overflowWrap: 'anywhere' }}>{choice}</Typography>
        <Button onClick={() => setOpen(false)}>Cancel</Button><Button variant="contained" disabled={!items.some(item => item.path === choice)} onClick={() => { onChange(choice); setOpen(false); }}>Use this method</Button>
      </DialogActions>
    </Dialog>
  </>;
}
