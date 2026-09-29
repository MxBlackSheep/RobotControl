# Documentation map

| Need | Start here |
| --- | --- |
| Setup, running and building the application | [Root README](../README.md) |
| Current frontend behavior and troubleshooting | `maintenance/frontend/` — choose the affected module |
| Current backend behavior and troubleshooting | `maintenance/backend/` — choose the affected module |
| Browser checks, fixture limits and repeat commands | [Browser run guide](../frontend/e2e/README.md) |
| What changed and why | [Implementation notes](implementation-notes.md), newest first |
| Open release work and review actions | [Release-readiness review](release-readiness-review-2026-09-29.md) — status table at the top |
| Findings behind the current engineering rules | [Engineering review](engineering-review-2026-09-27.md) |

Dated reviews and `plans/` record decisions and proposals at a point in time. They
do not impose permanent acceptance gates. For current behavior, read the module
guide and source. Local reports in `test-output/` and candidates in `dist/` are
Git-ignored evidence/output, not another documentation hierarchy.

Update an existing guide or scenario before adding a new one. Preserve historical
links; reorganize files only when it makes an actual maintenance task easier.
