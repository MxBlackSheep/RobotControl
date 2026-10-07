# Plate data export changes

## 1.0.0

First release as a RobotControl package. Exports every plate of one EvoYeast experiment to
Excel, as the desktop Plate Data Export tool does with all plates selected: Overview, Cultures,
Selection and Readings sheets, and one sheet per plate. Values are calculated by the upstream
code recorded in UPSTREAM.txt. Needs a read-only connection to the EvoYeast database and
RobotControl 0.1.5 or later (the Experiment list is newest first).

Differences from the desktop tool:

- Each plate sheet has a native Excel chart of OD over time instead of a picture: propagated
  cultures solid blue, not propagated dotted orange, a grey line at each propagation, a dot for a
  culture with a single reading. All cultures of one kind share one legend entry, so a plate with
  96 cultures still has a short legend. The OD axis is logarithmic with gridlines at doublings
  (0.031, 0.063, 0.125 ...), so the usual narrow OD range fills the chart. The chart's points are
  on a hidden "Chart data" sheet. A plate with no positive OD reading has no chart.
- The robot-ranking and growth-rate panels below the desktop plot are not drawn; their values are
  in the Selection sheet.
- No PNG folder is written, there is no plot preview and no plate choice.

Script adaptation (changes to the upstream code):

- plate_data_export.py (new): RobotControl's form definition and `run(context, inputs)`. It uses
  RobotControl's read-only connection, exports all plates, returns the workbook name, and stops
  with "This experiment has no plates to export." when the experiment has none.
- plate_report.py: the matplotlib figure functions are replaced by `time_course` (the figure's
  selection of points, unchanged) and `add_chart`; `export_plates` adds the chart where the
  picture was and no longer writes PNG files. The workbook functions are unchanged.
- plate_export.py: one line maps birth times through a dict, because the pandas bundled with
  RobotControl (3.x) cannot map through an empty datetime Series (a plate without parents) and
  stopped the report. The rows kept are the same.
- propagation_store.py and runtime.py keep only `query` and `discard_log`; the database,
  settings and log-file code is left out. propagation.py is unchanged.
