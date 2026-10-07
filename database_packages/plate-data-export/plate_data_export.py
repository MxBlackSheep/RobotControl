"""Plate data export: culture readings and the robot's propagation check, plate by plate.

RobotControl's version of PlateDataExport.py (see UPSTREAM.txt). It exports every plate of
the chosen experiment: an Overview sheet, Cultures, Selection and Readings sheets, and one
sheet per plate with its readings and a chart (propagated cultures solid, others dotted).
Read-only: the calculations in plate_export.py only run SELECT queries.
"""

from .plate_export import experiment_plates, load_experiment
from .plate_report import export_plates


TOOL = {
    "name": "Plate data export",
    "kind": "report",
    "connections": ["primary"],
    "inputs": {
        "experiment_id": {
            "label": "Experiment",
            "type": "integer",
            "query": "SELECT ExperimentID AS value, UserDefinedID AS label FROM dbo.Experiments",
            "order": "value_desc",
        },
    },
}


def run(context, inputs):
    experiment_id = inputs["experiment_id"]
    cursor = context.connection.cursor()
    try:
        plates = experiment_plates(cursor, experiment_id)
        if plates.empty:
            raise ValueError("This experiment has no plates to export.")
        # The desktop tool selects every plate by default; this report always exports them all.
        plate_ids = plates["PlateID"].tolist()
        data = load_experiment(cursor, experiment_id, plates, plate_ids)
    finally:
        cursor.close()
    return export_plates(data, plate_ids, context.output_dir).name
