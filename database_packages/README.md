# Add a report, operation or pre-run step from Python

**Write the tool once in Python. RobotControl builds its form and package.**
The author defines inputs, database relationships and behavior. The local
administrator chooses this lab's connections, tries the tool and enables it.

## Start with an example

The two existing EvoYeast tools are also ready as single Python files:

- [culture_history.py](culture-history/culture_history.py): the existing Culture history calculations and Excel formatting.
- [delete_experiment.py](delete-experiment/delete_experiment.py): preview and execution through `dbo.DeleteExperiment`.

For an installed tool, choose **Edit report/operation → Replace Python**, select
its `.py` file, check the connections, try, then **Publish update**. For a new
installation, use **Add tool** instead. No manifest or supporting file upload is
needed. Both use this lab's EvoYeast schema; they are not generic database tools.
Delete Experiment uses a reader for its experiment choices and an operation
connection to the **same database** for preview/execution.

In **Database → Manage packages → Add tool**, download **Report example** or
**Operation example**. Edit it yourself, optionally with a coding agent.

- [Report example](examples/report.py): Experiment → Plate choices and Excel output.
  It assumes `dbo.Experiments` and `dbo.Plates`; adapt the table/column names and
  replace its example output with your report's calculations.
- [Operation example](examples/operation.py): preview and delete one row in a
  disposable `dbo.DemoItems` table. It is not a laboratory deletion procedure.
  Adapt both functions before using it against real data.

An existing `Data.py` needs one adaptation: receive inputs and the supplied
connection, keep its calculations, and return its output filename. Upload does
not translate arbitrary Python. You do not create a manifest, name entry points,
specify a package version or construct a ZIP.

## What belongs in the Python

One literal `TOOL` dictionary describes the tool beside its functions:

```python
TOOL = {
    'name': 'My report',
    'kind': 'report',
    'inputs': {
        'experiment_id': {
            'label': 'Experiment', 'type': 'integer',
            'query': 'SELECT ExperimentID AS value, UserDefinedID AS label FROM dbo.Experiments',
        },
        'plate_id': {
            'label': 'Plate', 'type': 'integer',
            'query': 'SELECT PlateID AS value, CAST(PlateID AS nvarchar(40)) AS label FROM dbo.Plates WHERE ExpID = ?',
            'depends_on': ['experiment_id'],
        },
    },
}

def run(context, inputs):
    # Use context.connection and inputs['plate_id'] for your calculations.
    # Write Excel into context.output_dir and return its filename.
    ...
```

This excerpt illustrates the interface; the linked report example is complete.
Input names become the keys in `inputs`. Queries return `value` (the Python input)
and `label` (what the user sees). Each `?` receives the input at the corresponding
position in `depends_on`. Changing a parent clears its dependent choices; the
server checks membership again when running. Queries can use joins and your own
tables; no particular experiment or plate schema is required.

Ordinary fields can be concise: `'start_date': 'date'` or
`'format': {'type': 'choice', 'choices': ['Detailed', 'Summary']}`. Supported types
are text, integer, number, boolean, date, choice and experiment (a positive experiment ID,
offered from the primary connection's `dbo.Experiments`). Database choices use text,
integer or number plus `query`. Labels default from the input name; inputs are
required unless `required: False` is supplied.

Reports default to one read-only connection named `primary`. Set `connections: []`
for a report without a database, or `connections: ['primary', 'measurements']`
for several. Choose a dropdown source with `source: 'measurements'`. Python uses
`context.connections['measurements']`; `context.connection` is the primary connection.

An operation uses `kind: 'operation'`, `confirm: 'item_id'`, and both
`preview(context, inputs)` and `run(context, inputs)`. Preview returns
`{'summary': '...', 'details': {...}}`; it must only read. The operation database
is `context.connection`. Database dropdowns use separate read-only connections.
The host owns commit/rollback: do not commit inside your functions.

## Add, check and enable

1. **Add Python**: select the prepared file and any supporting files together.
   RobotControl reads the definition and ordinary imports without running them.
   The generated form appears beside source and connection controls.
2. Choose saved connections. Reports and dropdowns require readers; operations
   require a separate operation account. **Manage connections** opens setup; see
   the [database guide](../docs/maintenance/backend/database-maintenance-guide.md).
3. **Check setup**, then select inputs. **Try report** generates Excel to download
   and inspect. **Try preview** calls only the operation's preview, creates no
   execution confirmation and does not call its run function.
4. Review the Python and result, check the review box, and **Enable report** or
   **Enable operation**. It becomes available in Data retrieval or Operations.

Changing files or connections invalidates the trial. After reopening a draft or
restarting RobotControl, check and try again. **Save and close** retains work;
**Discard and close** removes the draft without touching installed tools.

Setup checks establish file, library and connection compatibility, not scientific
correctness. Trials execute trusted Python. A report label or separate process
does not sandbox filesystem/network access. Supplied report connections are
verified as read-only; uploaded Python still requires code review. Operations
retain local-admin access, robot/scheduler gates, target preview, typed confirmation,
transactions and duplicate-submission protection.

## Edit or move a tool

Choose **Edit report** or **Edit operation**, then **Download source**. Edit the
Python and choose **Replace Python**, try again, and **Publish update**. This replaces
the defining file even if its name changed, while keeping helpers. Under
**Supporting files**, use **Add supporting files** for helpers/data or **Replace all
files** to supply the complete new source set. The server rejects an incomplete
set without replacing the draft.
RobotControl retains identity, suggests a patch version and preserves sibling
tools by default. A changed installation or connection assignment blocks an old
draft. Custom entry functions outside `run`/`preview` still use the ZIP route.

The form's fields come from `TOOL['inputs']` in the defining Python; there is no
separate input settings file. `kind: 'report'` places it in Data retrieval;
`kind: 'operation'` places it in Operations.

**What changed?** is an optional publication note, saved with unfinished drafts.
Publishing returns to the installed list with a success message and removes the
completed draft. **History** shows version, time, publisher, note and filenames
added/changed/removed. History starts when recording is available; earlier changes
are not reconstructed. It is installation history, not retained source revisions
or rollback. Removing a package removes its local history. Use the single **Edit**
action for Python changes; **Import package ZIP** also handles ready-built updates.

Use **Export package** in the editor or **Download package** on an installed row
to move the complete tool. **Import package ZIP** retains the existing reviewed
package route; assign local connections after import. Saved passwords and local
assignments are not exported. Check authored Python for hard-coded secrets.

Supporting files stay in one flat folder: `.py`, `.json`, `.md` and `.txt`.
Use relative imports such as `from .calculations import build_workbook`, including
`calculations.py` when uploading. Multiple files download as a source ZIP: extract
it for editing, then select the files to upload. New additions require one TOOL
definition. Existing mixed packages retain other tools when one is edited.
Ordinary imports identify bundled libraries; dynamic imports cannot be inferred.
Unavailable libraries need an application upgrade.

Python/UV are not needed on deployment computers. Source uploads allow up to
3 MiB and 99 files; generated packages also follow [CONTRACT.md](CONTRACT.md).

## Run a step before a scheduled run

A **preparation** step is Python that RobotControl runs by itself before a scheduled
method starts, for example to record the run or set flags the method reads. Nobody is
present to review it at run time, so the rules are stricter than for operations:

- Write it as a package with `manifest.json` (contract version 2, `kind: "preparation"`,
  entry point `prepare(context, inputs)`). Start from
  [examples/preparation](examples/preparation), build it with the command below and
  install it under **Manage packages**; then assign its operation connection there.
  (The **Add tool** page does not offer a safe trial run for preparation steps yet.)
- Use `context.connection` and `context.run` (schedule, execution and experiment
  details). Do not commit or roll back; raise an exception to stop the run.
- A local administrator chooses the step and its inputs under **Before this run** in
  the schedule form. The schedule keeps that exact package version and connection.
- It must finish within two minutes. If it fails, times out or crashes, the run does
  not start, the schedule waits for recovery, and the step is never repeated
  automatically. Check the database before resuming.
- To update the package, first disable the schedules that use it, then save each
  schedule again so it uses the new version.

Packaging checks confirm structure and syntax only. They do not check the Python's
calculations or sandbox it: review it, and test it on a disabled schedule against a
disposable database before attaching it to real runs.

## Existing projects and drafts

Older report drafts resume in their original wizard. Existing ZIPs and the
command-line builder remain supported. For an existing source folder:

```powershell
uv run --locked python build_scripts/database_package.py build C:/Scripts/MyPackage --version 1.0.1
```

That advanced route uses an existing `manifest.json`; see [CONTRACT.md](CONTRACT.md).
New tools should use the Python-defined route above.
