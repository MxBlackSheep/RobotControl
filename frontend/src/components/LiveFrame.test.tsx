import React from 'react';
import { act, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import LiveFrame, { createFrameStore } from './LiveFrame';

it('updates both viewers without rerendering their page or retaining frame history', () => {
  const store = createFrameStore();
  let pageRenders = 0;
  function Page() {
    pageRenders++;
    return <><input aria-label="Draft" defaultValue="keep" /><LiveFrame store={store} alt="Normal" /><LiveFrame store={store} alt="Fullscreen" /></>;
  }
  const view = render(<Page />);
  const draft = screen.getByLabelText('Draft');
  draft.focus();
  for (let frame = 0; frame < 100; frame++) {
    act(() => store.set(`data:image/jpeg;base64,${frame}`));
  }
  expect(pageRenders).toBe(1);
  expect(screen.getByAltText('Normal').getAttribute('src')).toContain(',99');
  expect(screen.getByAltText('Fullscreen').getAttribute('src')).toContain(',99');
  expect(document.activeElement).toBe(draft);
  view.unmount();
  store.set(null);
  expect(store.getSnapshot()).toBeNull();
});
