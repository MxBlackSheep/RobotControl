"""Registration writes against a scratch SQL Server database, compared with RegisterNewExperiment.exe's own code.

Run (needs pyodbc; the comparison needs Shou_LHR's source, so use its interpreter):
  <Shou_LHR>\\.venv\\Scripts\\python.exe backend\\e2e\\experiment_registration_check.py <Shou_LHR checkout> <Shou_Lab checkout>
It creates EvoYeast_RCDev on .\\HAMILTON (Windows sign-in), builds the three tables from the writes and the saved
ScheduleExperimentForImmediateExecution text, and drops the database at the end. No other database is opened.
Types named by the saved lab definitions are used: UserDefinedID varchar(50) (GetUserExperimentID; ScheduleExperimentForImmediateExecution
and SpatialEvo_NewExperiment take varchar(255)), ParameterName varchar(50) (ReadExperimentParameter), WellID varchar(10).
Inferred, named nowhere: Note, ScheduledToRun, ParamValueTxt, WellAssign, ExperimentID and the keys; ExperimentPlatePattern is
referenced by no saved definition.

Failure cases: reused ID refused with nothing written; no culture well; bad TopFractionToPropagate; non-number
parameter; scheduling procedure error (rolls back every row); schedule 1 clears the other scheduled experiment;
rollback leaves no rows; rows equal the exe's rows for the same input.
"""
import sys
from pathlib import Path

import pyodbc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.services.experiments import register_experiment  # noqa: E402

DB = 'EvoYeast_RCDev'
SERVER = r'.\HAMILTON'
DRIVER = '{SQL Server Native Client 10.0}'
TABLES = """
CREATE TABLE Experiments (ExperimentID int IDENTITY(1,1) PRIMARY KEY, UserDefinedID varchar(50) NOT NULL,
    Note varchar(max) NULL, ScheduledToRun int NOT NULL DEFAULT 0);
CREATE TABLE ExperimentParameters (ExperimentID int NOT NULL, ParameterName varchar(50) NOT NULL, ParamValueTxt varchar(255) NULL);
CREATE TABLE ExperimentPlatePattern (ExperimentID int NOT NULL, WellID varchar(10) NOT NULL, WellAssign varchar(50) NOT NULL);
"""
PARAMETERS = {'BackgroundOD': 0.036, 'InoculationOD': 0.03, 'MaxIteration': 20, 'ODConversionFactor': 2.52,
              'FreezeVolume': 0.5, 'TargetWellVolume': 700, 'V_OD_Sample': 150, 'TopFractionToPropagate': 1,
              'FreezeGeneration': 1, 'UseFluorescence': 1, 'GFP_scale': 4669.1, 'GFP_RFPdamping': 773.1,
              'RFP_scale': 2262.3, 'RFP_GFPdamping': 305.0}
LAYOUT = [('A1', 'MediaCtrl'), ('A2', 'Cells'), ('B2', 'Cells')]


def connect(database):
    return pyodbc.connect(f'DRIVER={DRIVER};SERVER={SERVER};DATABASE={database};Trusted_Connection=yes;',
                          autocommit=False, timeout=10)


def rows(cursor, experiment_id):
    one = lambda sql: [tuple(r) for r in cursor.execute(sql, experiment_id).fetchall()]
    return (one('SELECT UserDefinedID, Note, ScheduledToRun FROM Experiments WHERE ExperimentID=?'),
            sorted((n, float(v)) for n, v in one('SELECT ParameterName, ParamValueTxt FROM ExperimentParameters WHERE ExperimentID=?')),
            sorted(one('SELECT WellID, WellAssign FROM ExperimentPlatePattern WHERE ExperimentID=?')))


def counts(cursor):
    return tuple(cursor.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                 for t in ('Experiments', 'ExperimentParameters', 'ExperimentPlatePattern'))


def main(lhr, lab):
    sys.path[:0] = [str(Path(lhr) / 'src'), str(Path(lhr) / 'VENUS Python Modules' / 'Champions_FL' / 'BeginNewExperiment')]
    import RegisterNewExperiment as exe  # the program being replaced
    procedure = (Path(lab) / 'tasks' / 'evoyeast_procedures_2026-11-17' / 'ScheduleExperimentForImmediateExecution.sql').read_text(encoding='utf-8-sig')
    master = pyodbc.connect(f'DRIVER={DRIVER};SERVER={SERVER};DATABASE=master;Trusted_Connection=yes;', autocommit=True, timeout=10)
    if master.execute('SELECT 1 FROM sys.databases WHERE name = ?', DB).fetchone():
        raise SystemExit(f'{DB} already exists; drop it yourself first.')
    master.execute(f'CREATE DATABASE {DB} COLLATE SQL_Latin1_General_CP1_CS_AS')
    failures = []
    try:
        setup = connect(DB)
        setup.autocommit = True
        for statement in TABLES.split(';'):
            if statement.strip():
                setup.execute(statement)
        setup.execute(procedure)
        setup.close()
        conn = connect(DB)
        cursor = conn.cursor()

        def check(name, condition):
            print(('ok   ' if condition else 'FAIL ') + name)
            if not condition:
                failures.append(name)

        def refused(call):
            before = counts(cursor)
            try:
                call()
            except Exception:
                conn.rollback()
                return counts(cursor) == before
            return False

        # Rows equal the exe's rows, for an unscheduled and a scheduled registration.
        for schedule in ('0', '1'):
            mine = register_experiment(conn, f'rc_{schedule}', 'note', schedule, PARAMETERS, LAYOUT)
            theirs = exe.insert_experiment(cursor, f'exe_{schedule}', 'note', schedule, PARAMETERS, LAYOUT)
            a, b = rows(cursor, mine), rows(cursor, theirs)
            check(f'schedule {schedule}: parameters and wells equal the exe', a[1:] == b[1:] and a[0][0][1] == b[0][0][1])
        check('schedule 1 left one scheduled experiment, the last', [r[0] for r in cursor.execute('SELECT UserDefinedID FROM Experiments WHERE ScheduledToRun=1')] == ['exe_1'])
        conn.rollback()
        check('rollback leaves no rows', counts(cursor) == (0, 0, 0))

        register_experiment(conn, 'taken', '', '0', PARAMETERS, LAYOUT)
        conn.commit()
        check('reused ID refused, nothing written', refused(lambda: register_experiment(conn, 'taken', '', '0', PARAMETERS, LAYOUT)))
        check('no culture well refused', refused(lambda: register_experiment(conn, 'n1', '', '0', PARAMETERS, [('A1', 'MediaCtrl')])))
        check('bad fraction refused', refused(lambda: register_experiment(conn, 'n2', '', '0', {**PARAMETERS, 'TopFractionToPropagate': 0.3}, LAYOUT)))
        check('non-number refused', refused(lambda: register_experiment(conn, 'n3', '', '0', {**PARAMETERS, 'MaxIteration': 'x'}, LAYOUT)))
        check('ID longer than the saved varchar(50) is refused, nothing written', refused(lambda: register_experiment(conn, 'x' * 51, '', '0', PARAMETERS, LAYOUT)))
        # A trigger that rejects the procedure's UPDATE makes scheduling report DATABASE ERROR.
        conn.execute('CREATE TRIGGER block_schedule ON Experiments AFTER UPDATE AS BEGIN RAISERROR(\'blocked\', 16, 1); END')
        conn.commit()
        check('procedure error rolls back every row', refused(lambda: register_experiment(conn, 'n4', '', '1', PARAMETERS, LAYOUT)))
        conn.close()
    finally:
        master.execute(f'ALTER DATABASE {DB} SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
        master.execute(f'DROP DATABASE {DB}')
        master.close()
    print('FAILED: ' + ', '.join(failures) if failures else 'all checks passed')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main(*sys.argv[1:3]))
