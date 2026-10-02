# Select EvoYeast experiment changes

## 1.0.0

First release as a RobotControl starter package. Replaces the former built-in EvoYeast schedule
preparation: before a scheduled run, marks one experiment ScheduledToRun and optionally runs
dbo.ResetHamiltonTables. Needs a read-only connection for the experiment list and an operation
connection to the same database for the changes.
