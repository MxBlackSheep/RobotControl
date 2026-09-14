import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { PageContent, PageHeader } from './PageLayout';
import NavigationBreadcrumbs from './NavigationBreadcrumbs';
function Location() { const location = useLocation(); return <output>{location.pathname + location.search}</output>; }
describe('Shared page layout', () => {
  it('keeps the page heading, actions and content accessible', () => {
    render(<PageContent><PageHeader title="Scheduling" actions={<button>Create schedule</button>} /><section aria-label="Runtime queue">No runs</section></PageContent>);
    expect(screen.getByRole('heading', { level: 1, name: 'Scheduling' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Create schedule' })).toBeTruthy();
    expect(screen.getByRole('region', { name: 'Runtime queue' })).toBeTruthy();
  });
  it('shows the section in one breadcrumb and returns to Schedules', async () => {
    render(<MemoryRouter initialEntries={['/scheduling?section=methods']}><NavigationBreadcrumbs compact showIcons={false} /><Location /></MemoryRouter>);
    expect(screen.getByText('Methods')).toBeTruthy();
    await userEvent.click(screen.getByRole('link', {name: 'Scheduling'}));
    expect(screen.getByRole('status').textContent).toBe('/scheduling');
    expect(screen.getByText('Schedules')).toBeTruthy();
  });
});
