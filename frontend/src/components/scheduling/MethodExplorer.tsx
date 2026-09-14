import React, { useMemo, useState } from 'react';
import { Box, Button, IconButton, Stack, TablePagination, TextField, Typography } from '@mui/material';
import { ChevronRight, ExpandMore, FolderOutlined } from '@mui/icons-material';
import { folderKey, inFolder, MethodFolder, MethodItem, methodFolders, relativeMethodPath } from './methodFolders';

export default function MethodExplorer<T extends MethodItem>({ items, initialPath = '', onViewChange, children }: {
  items: T[]; initialPath?: string; onViewChange?: () => void;
  children: (items: T[], relativePath: (path: string) => string) => React.ReactNode;
}) {
  const [folder, setFolder] = useState(() => initialPath ? folderKey(initialPath) : '');
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<string[]>(() => initialPath ? [folderKey(initialPath)] : []);
  const [foldersOpen, setFoldersOpen] = useState(true);
  const [mobileResults, setMobileResults] = useState(!!initialPath);
  const [page, setPage] = useState(() => Math.max(0, Math.floor(items.filter(item => inFolder(item.path, folderKey(initialPath))).findIndex(item => item.path === initialPath) / 25)));
  const [pageSize, setPageSize] = useState(25);
  const folders = useMemo(() => methodFolders(items), [items]);
  const shown = useMemo(() => items.filter(item => query.trim()
    ? `${item.name} ${item.path}`.toLowerCase().includes(query.trim().toLowerCase())
    : !!folder && inFolder(item.path, folder)), [items, query, folder]);
  const safePage = Math.min(page, Math.max(0, Math.ceil(shown.length / pageSize) - 1));
  const rows = shown.slice(safePage * pageSize, (safePage + 1) * pageSize);
  const choose = (key: string) => { setFolder(key); setQuery(''); setPage(0); setMobileResults(true); onViewChange?.(); };
  const toggle = (key: string) => setExpanded(old => old.some(value => value === key || value.startsWith(key + '\\')) ? old.filter(value => value !== key && !value.startsWith(key + '\\')) : [...old, key]);
  function renderFolder(node: MethodFolder, root = false): React.ReactNode {
    const open = expanded.includes(node.key) || expanded.some(key => key.startsWith(node.key + '\\'));
    return <Box component="li" role="treeitem" key={node.key} tabIndex={0} aria-label={node.path}
      aria-selected={folder === node.key} aria-expanded={node.children.length ? open : undefined}
      sx={{ listStyle: 'none', outlineOffset: -2 }} onKeyDown={event => {
        if (event.target !== event.currentTarget) return;
        const element = event.currentTarget;
        const visible = Array.from(element.closest('[role="tree"]')?.querySelectorAll<HTMLElement>('[role="treeitem"]') || []);
        const index = visible.indexOf(element);
        if (event.key === 'ArrowRight') { if (!open && node.children.length) toggle(node.key); else element.querySelector<HTMLElement>('[role="treeitem"]')?.focus(); }
        else if (event.key === 'ArrowLeft') { if (open && node.children.length) setExpanded(old => old.filter(key => key !== node.key && !key.startsWith(node.key + '\\'))); else element.parentElement?.closest<HTMLElement>('[role="treeitem"]')?.focus(); }
        else if (event.key === 'ArrowDown') visible[Math.min(index + 1, visible.length - 1)]?.focus();
        else if (event.key === 'ArrowUp') visible[Math.max(index - 1, 0)]?.focus();
        else if (event.key === 'Home') visible[0]?.focus();
        else if (event.key === 'End') visible[visible.length - 1]?.focus();
        else if (event.key === 'Enter' || event.key === ' ') choose(node.key);
        else return;
        event.preventDefault(); event.stopPropagation();
      }}>
      <Box onClick={() => choose(node.key)} sx={{ display: 'flex', alignItems: 'center', minHeight: 44, cursor: 'pointer', borderRadius: 1, bgcolor: folder === node.key ? 'action.selected' : undefined }}>
        {node.children.length ? <IconButton size="small" tabIndex={-1} aria-label={`${open ? 'Collapse' : 'Expand'} ${node.path}`} onClick={event => { event.stopPropagation(); toggle(node.key); }}>{open ? <ExpandMore /> : <ChevronRight />}</IconButton> : <FolderOutlined sx={{ mx: 1, flexShrink: 0 }} fontSize="small" />}
        <Typography variant="body2" title={node.path} sx={{ overflowWrap: 'anywhere', p: .5 }}>{root ? node.path : node.name}</Typography>
      </Box>
      {open && <Box component="ul" role="group" sx={{ pl: 2, m: 0 }}>{node.children.map(child => renderFolder(child))}</Box>}
    </Box>;
  }
  return <Box sx={{ containerType: 'inline-size', minWidth: 0 }}>
    <Stack spacing={1}>
      <TextField fullWidth size="small" label="Search all methods" value={query} onChange={event => { setQuery(event.target.value); setPage(0); setMobileResults(!!event.target.value || !!folder); onViewChange?.(); }} />
      <Stack direction="row" gap={1} alignItems="center">
        <Button size="small" onClick={() => { setFoldersOpen(value => !value); setMobileResults(false); }}>Folders</Button>
        <Typography variant="body2" sx={{ overflowWrap: 'anywhere' }}>{query.trim() ? 'Search results — all folders' : folder === '*' ? 'All methods' : folder === '!review' ? 'Needs path review' : folder ? items.find(item => folderKey(item.path) === folder)?.path.replace(/[\\/][^\\/]+$/, '') || folder : 'Choose a folder'}</Typography>
      </Stack>
      <Box sx={{ display: 'grid', gap: 2, minWidth: 0, '@container (min-width: 900px)': { gridTemplateColumns: foldersOpen ? '240px minmax(0, 1fr)' : 'minmax(0, 1fr)' } }}>
        <Box sx={{ display: mobileResults ? 'none' : 'block', '@container (min-width: 900px)': { display: foldersOpen ? 'block' : 'none' }, maxHeight: '55vh', overflow: 'auto' }}>
          <Button onClick={() => choose('*')}>All methods</Button>
          <Box component="ul" role="tree" aria-label="Imported method folders" sx={{ p: 0, m: 0 }}>{folders.map(node => renderFolder(node, true))}</Box>
          {!folders.length && <Typography>No imported folders.</Typography>}
        </Box>
        <Box sx={{ minWidth: 0, display: mobileResults || query ? 'block' : 'none', '@container (min-width: 900px)': { display: 'block' } }}>
          <Button size="small" sx={{ '@container (min-width: 900px)': { display: 'none' } }} onClick={() => setMobileResults(false)}>Back to folders</Button>
          {!folder && !query.trim() ? <Typography sx={{ p: 2 }}>Select a folder to see its methods, or search all methods above.</Typography> : <>
            <Typography variant="caption">{shown.length} methods</Typography>
            {children(rows, path => relativeMethodPath(path, query.trim() ? '*' : folder))}
            {!shown.length && <Typography sx={{ py: 2 }}>No methods match this view.</Typography>}
            <TablePagination component="div" count={shown.length} page={safePage} rowsPerPage={pageSize} rowsPerPageOptions={[25, 50, 100]}
              onPageChange={(_, next) => setPage(next)} onRowsPerPageChange={event => { setPageSize(Number(event.target.value)); setPage(0); }}
              sx={{ '& .MuiTablePagination-toolbar': { flexWrap: 'wrap', px: 0 }, '& .MuiTablePagination-spacer': { display: 'none' } }} />
          </>}
        </Box>
      </Box>
    </Stack>
  </Box>;
}
