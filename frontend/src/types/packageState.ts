/** Server-derived package usability, shared by packages and scheduled preparation. */
export const packageState = {
  needs_newer: { tone: 'attention', label: 'Needs newer RobotControl' },
  needs_review: { tone: 'attention', label: 'Needs review' },
  ready: { tone: 'completed', label: 'Installed' },
} as const;

export type PackageState = keyof typeof packageState;
