"""Delete one EvoYeast experiment through dbo.DeleteExperiment.

Add this file through RobotControl's Add tool, or replace the source when editing
the installed Delete Experiment operation. Use a read-only connection for choices
and the corresponding operation connection for preview/execution. RobotControl
owns the transaction, safety checks and typed confirmation.
"""

TOOL = {
    "name": "Delete Experiment",
    "kind": "operation",
    "connections": ["primary"],
    "confirm": "experiment_id",
    "inputs": {
        "experiment_id": {
            "label": "Experiment",
            "type": "integer",
            "query": "SELECT ExperimentID AS value, UserDefinedID AS label FROM dbo.Experiments",
            "order": "value_desc",
        },
    },
}


def preview(context, inputs):
    cursor = context.connection.cursor()
    try:
        cursor.execute("SELECT * FROM dbo.Experiments WHERE ExperimentID = ?", (inputs["experiment_id"],))
        row = cursor.fetchone()
        if row is None:
            raise ValueError("Experiment no longer exists. Refresh the selection.")
        experiment = dict(zip((column[0] for column in cursor.description), row))
        return {"summary": "Permanently delete this experiment and its associated data.",
                "details": experiment}
    finally:
        cursor.close()


def run(context, inputs):
    preview(context, inputs)  # Never rely on an earlier screen selection.
    cursor = context.connection.cursor()
    try:
        cursor.execute("EXEC dbo.DeleteExperiment @ExpID = ?", (inputs["experiment_id"],))
        # Consume all procedure results so SQL errors after an intermediate result surface.
        while cursor.nextset():
            pass
    finally:
        cursor.close()
    return {"message": "Experiment deleted."}
