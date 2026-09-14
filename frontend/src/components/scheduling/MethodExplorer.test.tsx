import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import MethodExplorer from './MethodExplorer';
import MethodPicker from './MethodPicker';
import { folderKey, inFolder, methodFolders, pathParts } from './methodFolders';

const many = Array.from({length: 1000}, (_, i) => ({id: String(i), name: `Method${String(i).padStart(4, '0')}`, path: `C:\\Methods\\Group${Math.floor(i / 100)}\\Method${String(i).padStart(4, '0')}.med`}));
const results = (items: typeof many) => <div>{items.map(item => <button key={item.id}>{item.name}</button>)}</div>;
it('builds compressed, case-insensitive folders while separating drives, UNC and legacy paths', () => {
  const folders = methodFolders([...many, {id: 'u', name: 'Same', path: '\\\\host\\share\\Nested\\Same.MED'}, {id: 'd', name: 'Same', path: 'D:\\Same.med'}, {id: 'l', name: 'Legacy', path: 'relative\\Same.med'}]);
  expect(folders.map(folder => folder.path)).toContain('C:\\Methods');
  expect(folders.map(folder => folder.path)).toContain('\\\\host\\share\\Nested');
  expect(folders.map(folder => folder.key)).toContain('!review');
  expect(folderKey('c:/METHODS/Group0/test.med')).toBe('c:\\methods\\group0');
  expect(inFolder('C:\\MethodsOther\\a.med', 'c:\\methods')).toBe(false);
  expect(pathParts('C:relative.med')).toBeNull();
});
it('starts with folders, renders only one page, and restores the folder after global search', () => {
  render(<MethodExplorer items={many}>{results}</MethodExplorer>);
  expect(screen.queryByRole('button', {name: 'Method0000'})).toBeNull();
  fireEvent.click(screen.getByRole('treeitem', {name: 'C:\\Methods'}).querySelector('div')!);
  expect(screen.getByRole('button', {name: 'Method0000'})).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Method0025'})).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'Go to next page'}));
  expect(screen.getByRole('button', {name: 'Method0025'})).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Search all methods'), {target: {value: 'Method0999'}});
  expect(screen.getByRole('button', {name: 'Method0999'})).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Search all methods'), {target: {value: ''}});
  expect(screen.getByRole('button', {name: 'Method0000'})).toBeTruthy();
});
it('opens the selected method page and preserves focus, search and scroll during refreshed data', () => {
  const view = render(<MethodExplorer items={many} initialPath={many[950].path}>{results}</MethodExplorer>);
  expect(screen.getByRole('button', {name: 'Method0950'})).toBeTruthy();
  const search = screen.getByLabelText('Search all methods') as HTMLInputElement;
  fireEvent.change(search, {target: {value: '0999'}}); search.focus();
  const tree = screen.getByRole('tree', {hidden: true}); tree.parentElement!.scrollTop = 100;
  for (let tick = 0; tick < 2; tick++) view.rerender(<MethodExplorer items={many.map(item => ({...item}))} initialPath={many[0].path}>{results}</MethodExplorer>);
  expect(document.activeElement).toBe(search); expect(search.value).toBe('0999');
  expect(tree.parentElement!.scrollTop).toBe(100);
});
it('supports keyboard expansion and selection', () => {
  render(<MethodExplorer items={many}>{results}</MethodExplorer>);
  const root = screen.getByRole('treeitem', {name: 'C:\\Methods'});
  root.focus(); fireEvent.keyDown(root, {key: 'ArrowRight'});
  const child = screen.getByRole('treeitem', {name: 'C:\\Methods\\Group0'});
  fireEvent.keyDown(root, {key: 'ArrowRight'}); expect(document.activeElement).toBe(child);
  fireEvent.keyDown(child, {key: 'Enter'});
  expect(screen.getByRole('button', {name: 'Method0000'})).toBeTruthy();
});
it.each(['Choose method', 'Choose cleanup method'])('%s only applies an explicitly confirmed choice', async label => {
  const change = vi.fn(); render(<MethodPicker methods={many} value="" label={label} onChange={change} />);
  fireEvent.click(screen.getByRole('button', {name: label}));
  fireEvent.change(screen.getByLabelText('Search all methods'), {target: {value: '0999'}});
  fireEvent.click(screen.getByRole('radio', {name: /Method0999/}));
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Use this method'}));
  expect(change).toHaveBeenCalledWith(many[999].path);
});
it('cancels a picker without replacing its saved path', () => {
  const change = vi.fn(); render(<MethodPicker methods={many} value={many[0].path} label="Choose method" onChange={change} />);
  fireEvent.click(screen.getByRole('button', {name: 'Choose method'}));
  fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
  expect(change).not.toHaveBeenCalled();
});
