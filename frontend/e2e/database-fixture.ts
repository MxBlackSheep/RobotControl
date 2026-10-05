import type { Page } from '@playwright/test';

/**
 * Faked read-only Database viewer answers shared by the behaviour specs and the screenshot review.
 * ViewerSamples holds the edge values the inspection checks assert; ActivePlateView has the
 * owner's real shape (32 rows, nine columns with OD last), which overflowed a phone sideways.
 */
export const viewerRows = Array.from({ length: 57 }, (_, index) => ({
  ID: index + 1,
  Name: `Sample ${String(index + 1).padStart(2, '0')}`,
  Notes: index === 0 ? 'Long complete value: ' + 'laboratory inspection '.repeat(50) : `Observation ${index + 1}`,
  Missing: null,
  Empty: '',
  LongColumnNameForResponsiveInspection: 'Preserved column value',
}));

export const activePlateRows = Array.from({ length: 32 }, (_, index) => ({
  PlateID: 9850 + index,
  Barcode: `EY${String(985000 + index * 7).padStart(8, '0')}`,
  ExperimentID: 42 + Math.floor(index / 8),
  CultureID: 98500000 + index,
  PlateType: index % 3 ? 'Greiner 96 F' : 'Corning 384',
  Position: `Cytomat ${1 + (index % 4)} / slot ${String(1 + index).padStart(2, '0')}`,
  Status: index % 5 ? 'Incubating' : 'Waiting for read',
  LastRead: `2026-09-30 ${String(8 + (index % 10)).padStart(2, '0')}:${String((index * 7) % 60).padStart(2, '0')}`,
  OD: (0.12 + index * 0.031).toFixed(3),
}));

export const procedureSql = '-- Inspection fixture\nCREATE PROCEDURE InspectSamples\n  @sample_id int,\n  @description nvarchar(200)\nAS\nBEGIN\n  SELECT * FROM Samples;\n  SELECT N\'Unicode Ω 中文\';\nEND;';

/** Answers like backend/api/database.py: search, column filters, sort direction and paging. */
function tableRoute(rows: Record<string, unknown>[]) {
  return async (route: Parameters<Parameters<Page['route']>[1]>[0]) => {
    const query = new URL(route.request().url()).searchParams;
    const search = query.get('search')?.toLowerCase();
    let selected = rows.filter(row => !search || Object.values(row).some(value => String(value).toLowerCase().includes(search)));
    const filters = JSON.parse(query.get('filters') || '{}') as Record<string, { value: string; operator: string }>;
    for (const [column, filter] of Object.entries(filters)) selected = selected.filter(row => String(row[column]).includes(filter.value));
    if (query.get('sort_direction') === 'desc') selected = [...selected].reverse();
    const limit = Number(query.get('limit') || 25), offset = (Number(query.get('page') || 1) - 1) * limit;
    await route.fulfill({ json: { success: true, data: { columns: Object.keys(rows[0]), rows: selected.slice(offset, offset + limit), total_count: selected.length } } });
  };
}

export async function routeDatabaseViewer(page: Page) {
  await page.route('**/api/database/tables?*', route => route.fulfill({ json: { success: true, data: {
    table_details: [{ name: 'ViewerSamples', has_data: true, is_important: true }, { name: 'EmptyTable', has_data: false, is_important: true },
      { name: 'dbo.ActivePlateView', has_data: true, is_important: false }],
  } } }));
  await page.route('**/api/database/tables/ViewerSamples?*', tableRoute(viewerRows));
  await page.route('**/api/database/tables/dbo.ActivePlateView?*', tableRoute(activePlateRows));
  await page.route('**/api/database/tables/EmptyTable?*', route => route.fulfill({ json: { success: true, data: { columns: ['ID'], rows: [], total_count: 0 } } }));
  await page.route('**/api/database/stored-procedures?*', route => route.fulfill({ json: { success: true, data: {
    procedures: [{ name: 'InspectSamples', type: 'PROCEDURE', definition: procedureSql, created_date: '2026-09-01T10:00:00', modified_date: '2026-09-20T12:00:00', parameters: [
      { name: '@sample_id', data_type: 'int', mode: 'IN', max_length: null },
      { name: '@description', data_type: 'nvarchar', mode: 'IN', max_length: 200 },
    ] }],
    functions: [{ name: 'SampleCount', type: 'FUNCTION', definition: 'CREATE FUNCTION SampleCount() RETURNS int AS BEGIN RETURN 57; END', parameters: [] }],
  } } }));
}
