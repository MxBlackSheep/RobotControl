"""Definition-driven registration in the caller's SQL Server transaction; never commits."""


def validate_registration(definition, user_defined_id, note, schedule, parameters, layout=None):
    if not isinstance(user_defined_id, str) or not user_defined_id.strip() or len(user_defined_id) > 255:
        raise ValueError('Enter a UserDefinedID of at most 255 characters.')
    if not isinstance(note, str) or len(note) > 4000:
        raise ValueError('Note must be at most 4000 characters.')
    if type(schedule) is not int or schedule not in (0, 1):
        raise ValueError('Invalid scheduling choice.')
    values = definition.validate_values(parameters)
    wells = definition.validate_layout(layout, values)
    return dict(user_defined_id=user_defined_id.strip(), note=note.strip(), schedule=schedule,
                parameters=values, layout=wells)


def register_experiment(connection, user_defined_id, note, schedule, parameters, layout, definition):
    clean = validate_registration(definition, user_defined_id, note, schedule, parameters, layout)
    user_defined_id = clean['user_defined_id']
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT ExperimentID FROM Experiments WITH (UPDLOCK, HOLDLOCK) WHERE UserDefinedID = ?', (user_defined_id,))
        matches = cursor.fetchall()
        if len(matches) > 1:
            raise ValueError(f"UserDefinedID '{user_defined_id}' matches more than one experiment.")
        reused_existing = bool(matches)
        if reused_existing:
            experiment_id = matches[0][0]
            populated = []
            cursor.execute('SELECT TOP 1 1 FROM ExperimentParameters WITH (UPDLOCK, HOLDLOCK) WHERE ExperimentID = ?', (experiment_id,))
            if cursor.fetchone() is not None:
                populated.append('parameters')
            if definition.layout is not None:
                cursor.execute('SELECT TOP 1 1 FROM ExperimentPlatePattern WITH (UPDLOCK, HOLDLOCK) WHERE ExperimentID = ?', (experiment_id,))
                if cursor.fetchone() is not None:
                    populated.append('plate layout')
            if populated:
                raise ValueError(f"UserDefinedID '{user_defined_id}' already has {' and '.join(populated)}.")
        else:
            cursor.execute('INSERT INTO Experiments (UserDefinedID, Note, ScheduledToRun) '
                           'OUTPUT INSERTED.ExperimentID VALUES (?, ?, ?)',
                           (user_defined_id, clean['note'], schedule))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError('Could not retrieve ExperimentID.')
            experiment_id = row[0]
        for name, value in clean['parameters'].items():
            cursor.execute('INSERT INTO ExperimentParameters (ExperimentID, ParameterName, ParamValueTxt) VALUES (?, ?, ?)',
                           (experiment_id, name, value))
        if clean['layout']:
            cursor.executemany('INSERT INTO ExperimentPlatePattern (ExperimentID, WellID, WellAssign) VALUES (?, ?, ?)',
                               [(experiment_id, well, assignment) for well, assignment in clean['layout']])
        if schedule == 1:
            cursor.execute('EXEC dbo.ScheduleExperimentForImmediateExecution @UserDefinedExptID = ?', (user_defined_id,))
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
        return dict(experiment_id=experiment_id, user_defined_id=user_defined_id,
                    reused_existing=reused_existing)
    finally:
        cursor.close()
