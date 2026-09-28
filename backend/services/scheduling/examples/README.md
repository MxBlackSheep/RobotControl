# Scheduling with a different laboratory database

RobotControl retains its own SQLite schedule/recovery records and the Hamilton
run reader. Only laboratory preparation changes. This example is a second schema,
not a second laboratory or robot validation.

## Existing lab

Leave `data/scheduling-lab.json` absent to retain the native EvoYeast connection.
Existing `ScheduledToRun` + `EvoYeastExperiment:42|set` schedules need no conversion.
The first token is an old form marker; the second identifies the actual SQL write.
The selection remains active after the method finishes, as before.

To use the same EvoYeast schema on a different SQL Server, create an **operation**
connection in Database → Manage packages → Connections. While the scheduler is
idle and recovery is resolved, disable schedules, stop RobotControl, and create:

```json
{"adapter": "evoyeast", "source_id": "your-operation-connection-id"}
```

Restart RobotControl. This changes laboratory preparation only; it does not
redirect Hamilton run monitoring, Tip tracking or Cytomat. Connection profiles
are captured at restart, so editing a profile cannot redirect a running method.
Schedules retain their original database binding. If the database target changes,
re-create schedules after reviewing preparation; simply enabling an old schedule
will not transfer it. Rotating credentials on the same target retains the binding.
If startup reports an unfinished job or recovery, restore the previous configuration
and reconcile that work first. Never clear scheduler tables to bypass this hold.

## Disposable batch example

Use a separate candidate installation with no live robot methods/schedules.
Create a new `data/batches.db` SQLite file using `batch-schema.sql` from this folder.
For example, in a development checkout:

```powershell
@'
import sqlite3
from pathlib import Path
path = Path('data/batches.db')
if path.exists():
    raise SystemExit('Choose a new file; existing data will not be replaced.')
conn = sqlite3.connect(path)
try:
    conn.executescript(Path('backend/services/scheduling/examples/batch-schema.sql').read_text())
    conn.commit()
finally:
    conn.close()
'@ | uv run --locked python -
```

Create `data/scheduling-lab.json`:

```json
{"adapter": "batch-sqlite", "sqlite_path": "batches.db"}
```

Restart. Schedule preparation now offers **Batch** choices. Selecting B-02 stores
`Batch:B-02`; preparation verifies the batch is ready and assigns the method to
`InstrumentWorkOrder` slot 1. It does not alter EvoYeast flags or consume the batch.
This example does not teach a Hamilton method to read that table: a real lab must
implement and validate that method-side agreement before running hardware.

SQLite can be prepared with any SQLite tool; Python is not required on deployment
computers. Relative paths resolve inside the application's `data` directory.
Missing files are rejected rather than silently creating an empty database.

## Writing another integration

Start with the two classes in `../lab_integration.py`. An adapter supplies concise
form labels, `choices(limit)`, `validate(steps)` and `prepare(experiment, steps)`.
It owns its table names, parameterized SQL and transaction. Add it explicitly to
`load_lab_integration`; this first version is reviewed application code and requires
a new build. There is no scheduler Python upload mechanism.

Keep queueing, retry decisions, run matching and recovery in RobotControl. Add new
inputs only when an actual lab workflow needs them. Do not change current lab SQL
to imitate the batch schema or add a universal column-mapping language.

Preparation cannot transact atomically with robot launch. RobotControl records the
attempt before calling the adapter, blocks duplicate execution IDs and requests
manual recovery if preparation fails after the attempt begins. A stored procedure
that commits internally or writes outside its transaction needs its own documented
recovery procedure. It must not be described as automatically reversible.
