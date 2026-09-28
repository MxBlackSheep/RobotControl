"""Adapt the table/column names and calculation below to your database.

Upload this file in Add tool. RobotControl reads TOOL without running Python.
The primary connection is selected by the administrator; do not put passwords here.
"""
from openpyxl import Workbook

TOOL = {
    'name': 'Plate history export',
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
    # Replace this query/output with your scientific report, preserving its rules.
    with context.connection.cursor() as cursor:
        rows = cursor.execute('SELECT * FROM dbo.Plates WHERE PlateID = ? AND ExpID = ?',
                              (inputs['plate_id'], inputs['experiment_id'])).fetchall()
        columns = [column[0] for column in cursor.description]
    workbook = Workbook()
    workbook.active.title = 'Plate'
    workbook.active.append(columns)
    for row in rows:
        workbook.active.append(list(row))
    filename = f"Plate_{inputs['plate_id']}.xlsx"
    workbook.save(context.output_dir / filename)
    return filename
