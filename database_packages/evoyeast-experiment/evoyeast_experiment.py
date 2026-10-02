"""Before a scheduled run: mark the chosen EvoYeast experiment ScheduledToRun, and no other.

This replaces RobotControl's former built-in EvoYeast preparation with the same SQL: clear
ScheduledToRun on every experiment, then set it on the chosen one. Assign a read-only
connection (experiment choices) and an operation connection to the same EvoYeast database in
Database settings, then attach it to a schedule under **Before this run**. RobotControl runs
it in one SERIALIZABLE transaction and commits after prepare() returns; raising rolls
everything back and stops the run.
"""

TOOL = {
    "name": "Select EvoYeast experiment",
    "kind": "preparation",
    "inputs": {
        "experiment_id": {
            "label": "Experiment",
            "type": "integer",
            "query": "SELECT ExperimentID AS value, COALESCE(UserDefinedID + N' (', N'(') + CAST(ExperimentID AS nvarchar(40)) + N')' AS label FROM dbo.Experiments",
        },
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


def prepare(context, inputs):
    cursor = context.connection.cursor()
    try:
        return {"message": select_experiment(cursor, inputs["experiment_id"])}
    finally:
        cursor.close()
