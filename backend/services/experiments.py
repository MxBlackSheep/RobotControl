"""Champions registration in the caller's SQL Server transaction; never commits."""
import math
import re


def register_experiment(connection, user_id, note, schedule, parameters, layout):
    user_id = user_id.strip()
    if not user_id:
        raise ValueError('Enter an experiment ID.')
    values = {}
    for name, value in parameters.items():
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f'{name} must be a finite number.') from None
        if not math.isfinite(number):
            raise ValueError(f'{name} must be a finite number.')
        values[name] = number
    if values.get('TopFractionToPropagate') not in (0.25, 0.5, 1):
        raise ValueError('TopFractionToPropagate must be 0.25, 0.5 or 1 (25%, 50% or 100%).')
    layout = list(layout)
    seen = set()
    for well, assignment in layout:
        if not re.fullmatch(r'[A-H](?:[1-9]|1[0-2])', well) or well in seen:
            raise ValueError('Invalid or duplicate well.')
        if assignment not in ('Cells', 'MediaCtrl'):
            raise ValueError('Invalid well assignment. Omit empty wells.')
        seen.add(well)
    if not any(assignment == 'Cells' for _, assignment in layout):
        raise ValueError('Mark at least one culture well.')
    if str(schedule) not in ('0', '1'):
        raise ValueError('Invalid scheduling choice.')
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT ExperimentID FROM Experiments WITH (UPDLOCK, HOLDLOCK) WHERE UserDefinedID = ?', (user_id,))
        if cursor.fetchone() is not None:
            raise ValueError('An experiment with this ID already exists.')
        cursor.execute('INSERT INTO Experiments (UserDefinedID, Note, ScheduledToRun) '
                       'OUTPUT INSERTED.ExperimentID VALUES (?, ?, ?)', (user_id, note.strip(), int(schedule)))
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError('Could not retrieve ExperimentID.')
        experiment_id = row[0]
        for name, value in values.items():
            cursor.execute('INSERT INTO ExperimentParameters (ExperimentID, ParameterName, ParamValueTxt) VALUES (?, ?, ?)',
                           (experiment_id, name, value))
        cursor.executemany('INSERT INTO ExperimentPlatePattern (ExperimentID, WellID, WellAssign) VALUES (?, ?, ?)',
                           [(experiment_id, well, assignment) for well, assignment in layout])
        if int(schedule) == 1:
            cursor.execute('EXEC dbo.ScheduleExperimentForImmediateExecution @UserDefinedExptID = ?', (user_id,))
            while True:
                if cursor.description:
                    for result in cursor.fetchall():
                        if any('DATABASE ERROR' in str(value) for value in result):
                            raise ValueError(f'Scheduling failed: {result[0]}')
                if not cursor.nextset():
                    break
        cursor.execute('SELECT @@TRANCOUNT')
        if cursor.fetchone()[0] < 1:
            raise RuntimeError('Experiment registration transaction is no longer active.')
        return experiment_id
    finally:
        cursor.close()
