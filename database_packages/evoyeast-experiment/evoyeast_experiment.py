"""Before a scheduled run: mark one EvoYeast experiment ScheduledToRun, optionally reset tables.

This replaces RobotControl's former built-in EvoYeast preparation with the same SQL.
Assign a read-only connection (experiment choices) and an operation connection to the
same EvoYeast database in Database settings, then attach it to a schedule under
**Before this run**. RobotControl runs it in one SERIALIZABLE transaction and commits
after prepare() returns; raising rolls everything back and stops the run.

dbo.ResetHamiltonTables must already exist when a schedule resets tables. It receives
the scheduled method's name and, when tables are listed, @TablesJson (a JSON array).
"""
import json

TOOL = {
    "name": "Select EvoYeast experiment",
    "kind": "preparation",
    "inputs": {
        "experiment_id": {
            "label": "Experiment",
            "type": "integer",
            "required": False,
            "query": "SELECT ExperimentID AS value, COALESCE(UserDefinedID + N' (', N'(') + CAST(ExperimentID AS nvarchar(40)) + N')' AS label FROM dbo.Experiments",
        },
        "reset_tables": {"label": "Reset Hamilton tables", "type": "boolean", "required": False},
        "table_list": {"label": "Tables to reset (comma-separated; blank resets all)", "type": "text", "required": False},
        "reset_first": {"label": "Reset tables before selecting the experiment", "type": "boolean", "required": False},
    },
}


def select_experiment(cursor, experiment_id):
    # Lock the target before clearing any flags; reject a missing or duplicated ID.
    cursor.execute("SELECT ExperimentID FROM dbo.Experiments WITH (UPDLOCK, HOLDLOCK) WHERE ExperimentID = ?", experiment_id)
    if len(cursor.fetchall()) != 1:
        raise ValueError(f"Experiment {experiment_id} is missing or not unique. Choose it again in the schedule.")
    cursor.execute("UPDATE dbo.Experiments SET ScheduledToRun = 0")
    cursor.execute("UPDATE dbo.Experiments SET ScheduledToRun = 1 WHERE ExperimentID = ?", experiment_id)
    if cursor.rowcount != 1:
        raise ValueError("The selected experiment changed during preparation.")
    return f"Experiment {experiment_id} marked ScheduledToRun"


def reset_tables(cursor, method_name, table_list):
    tables = [name.strip() for name in table_list.split(",")] if table_list.strip() else []
    if any(not name for name in tables):
        raise ValueError("Invalid reset table list: remove the empty entry.")
    if tables:
        cursor.execute("EXEC dbo.ResetHamiltonTables @ExperimentName = ?, @TablesJson = ?", method_name, json.dumps(tables))
    else:
        cursor.execute("EXEC dbo.ResetHamiltonTables @ExperimentName = ?", method_name)
    # Consume every result so an error raised after an intermediate result surfaces.
    while cursor.nextset():
        pass
    return "Hamilton tables reset" + (f" ({', '.join(tables)})" if tables else "")


def prepare(context, inputs):
    table_list = inputs.get("table_list") or ""
    if table_list.strip() and not inputs.get("reset_tables"):
        raise ValueError("Tables are listed but Reset Hamilton tables is off. Review the schedule.")
    steps = []
    if inputs.get("experiment_id") is not None:
        steps.append(lambda cursor: select_experiment(cursor, inputs["experiment_id"]))
    if inputs.get("reset_tables"):
        steps.append(lambda cursor: reset_tables(cursor, context.run.experiment_name, table_list))
    if inputs.get("reset_first"):
        steps.reverse()
    cursor = context.connection.cursor()
    try:
        done = [step(cursor) for step in steps]
    finally:
        cursor.close()
    return {"message": "; ".join(done) or "Nothing selected: no experiment flag or table reset."}
