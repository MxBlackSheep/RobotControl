# Delete Experiment changes

## 1.0.1

The Experiment list shows the newest experiments first (by ExperimentID, highest first)
instead of alphabetically by name. Search still matches the name.

Needs RobotControl 0.1.5 or later. A package cannot declare a minimum application version,
so an older RobotControl refuses this ZIP on import (the message names `lookup.order`) and
keeps 1.0.0 installed.

## 1.0.0

First release as a RobotControl starter package. Previews and then deletes one EvoYeast
experiment through dbo.DeleteExperiment. Needs a read-only connection for the experiment list
and an operation connection to the same database for the deletion.
