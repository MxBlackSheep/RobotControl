# Plate data export

A RobotControl report (Data retrieval → **Plate data export**). Choose an experiment; the
report writes the desktop Plate Data Export workbook for all of its plates, with a native Excel
chart on each plate sheet. It only reads (SELECT). CHANGELOG.md lists what differs from the
desktop tool and every change to the upstream code.

## Files

- `plate_data_export.py`: the form (`TOOL`) and `run(context, inputs)`. RobotControl-only.
- `plate_export.py`, `propagation.py`, `propagation_store.py`, `runtime.py`: upstream
  calculations, copied from `src/hamilton_workflows` (UPSTREAM.txt names the version).
- `plate_report.py`: upstream workbook code, with the chart in place of the matplotlib figure.

## Updating from upstream

1. Copy the changed upstream files over these, then put back the marked "RobotControl package"
   changes listed under "Script adaptation" in CHANGELOG.md. Use only pandas, openpyxl, pyodbc,
   numpy and the standard library; import the other files with `from .name import ...`.
2. Record the new upstream commit in UPSTREAM.txt.
3. Compare with the desktop tool: `uv run --locked python backend/e2e/plate_export_check.py`
   in the RobotControl repository. It runs the report and upstream's `export_plates` on a
   disposable copy of the EvoYeast data and compares every cell and chart point.
4. Add a `## <version>` section to CHANGELOG.md, then build the ZIP (package building is
   separate from the script changes above):
   `uv run --locked python build_scripts/database_package.py build database_packages/plate-data-export --version <version>`
   This checks structure and Python syntax only, not the calculations.
5. Install it under Database → Manage packages → Add package (or Update).
