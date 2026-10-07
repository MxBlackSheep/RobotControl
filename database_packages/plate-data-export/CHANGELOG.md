# Plate data export changes

## 1.1.1

A plate with no propagation yet (a round in progress) had a broken time-course chart in Excel:
the legend listed every reading as its own entry, named after its hour (0, 0.46, 4.47 ...),
the plot was pushed to the bottom, and the dotted lines turned into vertical hatching. Cause:
openpyxl wrote no varyColors setting, Excel treats a missing one as on, and such a plate's chart
has a single series ("Not propagated"), which Excel then colours and lists point by point.
Plates with a propagation always have two or more series, which hid it. Every chart now sets
varyColors off. No calculation or sheet value changes.

## 1.1.0

Each plate sheet now also has the desktop figure's two lower panels, as native Excel charts.
Under the time course, each propagation gets the figure's summary line (for example
"Propagation 1, 2026-09-26 13:40: 16 of 32 propagated, ranking check PASS, growth agreement
8/16") and two charts side by side:

- **Robot ranking: OD at propagation, highest first**: one bar per culture in robot-rank order,
  labelled with its well. Propagated bars are solid blue; not propagated bars have an orange
  outline and an orange dotted pattern (the figure's dot hatch), so the two stay apart in
  greyscale. A dark vertical line after the robot's top N marks its cutoff, named in the legend
  ("Robot cutoff: top 16"); red crosses mark cultures where the robot rule disagrees. As in the
  figure, there is no cutoff or cross when the ranking check is N/A.
- **Growth rate vs OD at propagation**: propagated cultures as filled blue points, not
  propagated as open orange points; axes "OD at propagation" and "Growth rate (ln OD per hour)".

A plate with several propagations gets one line and pair of charts per propagation, one under
another. A plate without one has the line "No propagation recorded from this plate yet" and no
ranking or growth charts. The values come from the same Selection rows the desktop figure plots.

Script adaptation (changes to the upstream code), in plate_report.py only:

- `event_summary` is copied from upstream unchanged. `event_panels` picks each propagation's
  Selection rows as upstream's `plate_figure`, `_ranking` and `_growth` do; `add_ranking_chart`,
  `add_growth_chart` and `add_panels` draw them in place of the matplotlib panels.
- `add_chart` (time course) shares its title, axis and marker styling with the new charts; it
  draws the same chart as 1.0.0.

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
