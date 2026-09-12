import { describe, expect, it } from 'vitest';
import { getRunStateDisplay } from './ExperimentStatus';

describe('Hamilton status display', () => {
  it.each([1, '1', 'Running'])('labels %s as Running', value => {
    expect(getRunStateDisplay(value).label).toBe('Running');
  });
  it.each([2, '2', 'Paused'])('labels %s as Paused', value => {
    expect(getRunStateDisplay(value).label).toBe('Paused');
    expect(getRunStateDisplay(value).animate).not.toBe(true);
  });
});
