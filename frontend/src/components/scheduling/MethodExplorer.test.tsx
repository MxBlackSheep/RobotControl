import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import MethodPicker from './MethodPicker';

// Failure cases: a robot method or cleanup method changes before confirmation,
// or cancelling the picker replaces the previously saved path.
const many = [
  { id: '0', name: 'Method0000', path: 'C:\\Methods\\Method0000.med' },
  { id: '1', name: 'Method0999', path: 'C:\\Methods\\Method0999.med' },
];
it.each(['Choose method', 'Choose cleanup method'])('%s only applies an explicitly confirmed choice', async label => {
  const change = vi.fn(); render(<MethodPicker methods={many} value="" label={label} onChange={change} />);
  fireEvent.click(screen.getByRole('button', {name: label}));
  fireEvent.change(screen.getByLabelText('Search all methods'), {target: {value: '0999'}});
  fireEvent.click(screen.getByRole('radio', {name: /Method0999/}));
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', {name: 'Use this method'}));
  expect(change).toHaveBeenCalledWith(many[1].path);
});
it('cancels a picker without replacing its saved path', () => {
  const change = vi.fn(); render(<MethodPicker methods={many} value={many[0].path} label="Choose method" onChange={change} />);
  fireEvent.click(screen.getByRole('button', {name: 'Choose method'}));
  fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
  expect(change).not.toHaveBeenCalled();
});
