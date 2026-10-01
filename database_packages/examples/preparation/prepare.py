"""Example preparation step: record each scheduled run before the robot starts.

Runs unattended, before the method launches, in a separate process with a two-minute
limit. RobotControl opens context.connection (the package's operation connection), sets
SERIALIZABLE with XACT_ABORT, and commits only after prepare() returns. Do not commit,
roll back or open other connections here. Raise an exception to stop the run: nothing
is committed and the schedule waits for an operator's recovery decision.

Create the table once, yourself, before attaching this step to a schedule:

    CREATE TABLE dbo.ScheduledRunLog (
        ExecutionID nvarchar(64) NOT NULL PRIMARY KEY,
        ScheduleID nvarchar(64) NOT NULL,
        ExperimentName nvarchar(200) NOT NULL,
        PreparedAt datetime2 NOT NULL,
        Note nvarchar(2000) NULL)
"""


def prepare(context, inputs):
    run = context.run  # schedule_id, execution_id, experiment_name, experiment_path, scheduled_for, started_at
    cursor = context.connection.cursor()
    cursor.execute(
        "INSERT INTO dbo.ScheduledRunLog (ExecutionID, ScheduleID, ExperimentName, PreparedAt, Note) "
        "VALUES (?, ?, ?, SYSUTCDATETIME(), ?)",
        run.execution_id, run.schedule_id, run.experiment_name, inputs.get("note"))
    return {"message": f"Recorded {run.experiment_name}"}
