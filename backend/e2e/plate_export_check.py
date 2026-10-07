"""Plate data export package against the desktop tool, through RobotControl on real SQL Server.

Run: uv run --locked python backend/e2e/plate_export_check.py [--upstream C:/path/Shou_LHR_PythonPackage]
     [--source-database EvoYeast] [--experiment 326 ...]
Requires a local SQL Server administrator via Windows authentication (.\\HAMILTON) and a checkout
of the upstream repository with its own .venv (pandas 2, matplotlib). Copies the eight EvoYeast
objects the report reads into a disposable database with a SELECT-only login; the source database
is only read. Builds the ZIP with build_scripts/database_package.py, installs it through the HTTP
API, runs the report for every experiment and compares it with upstream plate_report.export_plates
(the desktop tool's export) run on the same disposable data. Evidence: test-output/plate-export-check.

Failure cases:
- Under RobotControl's pandas the report crashes, or computes different Overview, Cultures,
  Selection, Readings or plate-sheet values from the desktop tool (cells compared exactly).
- The chart leaves out or invents readings: its points differ from the positive OD readings the
  desktop figure plots, a culture lands in the wrong propagated group, a lone reading is not a dot,
  or propagation lines are missing. A plate with readings has no chart.
- The Experiment list is not newest first; an experiment without plates fails with a raw error
  instead of a short message.
- The output folder keeps upstream's PNG folder beside the workbook.
Not covered: chart appearance (inspect a workbook), the ranking/growth panels (not reproduced),
the lab's SQL Server version and data.
"""
from contextlib import contextmanager
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import zipfile

import openpyxl
import pyodbc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from backend.api.database_tools import router
from backend.services.auth import get_current_user
from backend.services.database_tools import DatabaseTools, get_database_tools

EVIDENCE = ROOT / 'test-output/plate-export-check'
PACKAGE = ROOT / 'database_packages/plate-data-export'
BASE = '/api/database/tools'
SERVER = r'.\HAMILTON'
TABLES = ('Experiments', 'AncestPlatesInExperiments', 'Plates', 'Cultures', 'CulturesHistory',
          'ChampionsCulturesHistory', 'Propagation', 'ExperimentParameters')
CHART_DATA = 'Chart data'

REFERENCE = r'''
import json, sys
from pathlib import Path
import pyodbc
from hamilton_workflows import plate_export, plate_report
connection_string, out, experiments = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])
result = {}
with pyodbc.connect(connection_string) as conn:
    for experiment_id in experiments:
        # As PlateDataExport.py: list the experiment's plates, export them all.
        plates = plate_export.experiment_plates(conn.cursor(), experiment_id)
        if plates.empty:
            result[experiment_id] = None
            continue
        ids = [int(p) for p in plates["PlateID"]]
        data = plate_export.load_experiment(conn.cursor(), experiment_id, plates, ids)
        folder = out / str(experiment_id)
        folder.mkdir(parents=True)
        result[experiment_id] = str(plate_report.export_plates(data, ids, folder))
print(json.dumps(result))
'''


@contextmanager
def sql_fixture(source_database):
    suffix = uuid.uuid4().hex[:12]
    login = name = 'rc_plate_export_' + suffix
    password = secrets.token_urlsafe(32)
    admin = pyodbc.connect(f'DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE=master;Trusted_Connection=yes;TrustServerCertificate=yes', timeout=5, autocommit=True)
    created = False
    try:
        admin.execute(f"CREATE LOGIN [{login}] WITH PASSWORD='{password}', CHECK_POLICY=OFF")
        admin.execute(f'CREATE DATABASE [{name}]'); created = True
        for table in TABLES:
            admin.execute(f'SELECT * INTO [{name}].dbo.[{table}] FROM [{source_database}].dbo.[{table}]')
        definition = admin.execute(f"SELECT definition FROM [{source_database}].sys.sql_modules WHERE object_id=OBJECT_ID('[{source_database}].dbo.Descendants')").fetchone()[0]
        admin.execute(f'USE [{name}]')
        admin.execute(definition)
        admin.execute(f'CREATE USER [{login}] FOR LOGIN [{login}]')
        admin.execute(f'GRANT SELECT TO [{login}]')
        admin.execute('USE master')
        yield dict(database=name, login=login, password=password)
    finally:
        admin.execute('USE master')
        if created:
            admin.execute(f'ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            admin.execute(f'DROP DATABASE [{name}]')
        for (session,) in admin.execute('SELECT session_id FROM sys.dm_exec_sessions WHERE login_name=?', login).fetchall():
            admin.execute(f'KILL {int(session)}')
        if admin.execute('SELECT 1 FROM sys.server_principals WHERE name=?', login).fetchone():
            admin.execute(f'DROP LOGIN [{login}]')
        admin.close()


def sheet_values(book, name):
    return [list(row) for row in book[name].iter_rows(values_only=True)]


def compare(reference, package):
    """Cell-value differences between the desktop and package workbooks (charts/images ignored)."""
    expected, actual = openpyxl.load_workbook(reference), openpyxl.load_workbook(package)
    names = [n for n in actual.sheetnames if n != CHART_DATA]
    problems = [] if expected.sheetnames == names else [f'sheets {expected.sheetnames} != {names}']
    for name in set(expected.sheetnames) & set(names):
        want, got = sheet_values(expected, name), sheet_values(actual, name)
        if len(want) != len(got):
            problems.append(f'{name}: {len(want)} rows, package {len(got)}')
        for row, (a, b) in enumerate(zip(want, got), 1):
            if a != b:
                problems.append(f'{name} row {row}: {a} != {b}')
                break
    return problems


def chart_points(reference, package):
    """The package's chart data against the readings the desktop figure plots, per plate."""
    readings = sheet_values(openpyxl.load_workbook(reference), 'Readings')
    header, rows = readings[0], readings[1:]
    col = {h: i for i, h in enumerate(header)}
    expected = {}
    for plate, culture in dict.fromkeys((r[col['Plate']], r[col['CultureID']]) for r in rows):
        points = [(r[col['cumulative Time']], r[col['OD']]) for r in rows
                  if r[col['Plate']] == plate and r[col['CultureID']] == culture and r[col['OD']] is not None and r[col['OD']] > 0]
        if not points:
            continue
        propagated = next(r[col['Propagated']] for r in rows if r[col['Plate']] == plate and r[col['CultureID']] == culture) == 'Yes'
        group = ('Propagated' if propagated else 'Not propagated') + (', one reading' if len(points) == 1 else '')
        expected.setdefault(plate, {}).setdefault(group, Counter()).update(points)
    overview = sheet_values(openpyxl.load_workbook(reference), 'Overview')
    events = {r[0]: len(r[overview[0].index('Propagation time')].split('; ')) if r[overview[0].index('Propagation time')] else 0
              for r in overview[1:]}

    book = openpyxl.load_workbook(package)
    actual, lines = {}, {}
    if CHART_DATA in book.sheetnames:
        data = book[CHART_DATA]
        assert data.sheet_state == 'hidden'
        for column in range(1, data.max_column + 1, 2):
            label = data.cell(1, column).value
            plate, group = label.removeprefix('Plate ').removesuffix(' hours').split(' ', 1)
            values = [(data.cell(r, column).value, data.cell(r, column + 1).value) for r in range(2, data.max_row + 1)]
            if group == 'Propagation':
                runs = sum(1 for i, v in enumerate(values) if v[0] is not None and (i == 0 or values[i - 1][0] is None))
                lines[int(plate)] = runs
            elif any(x is not None for x, _ in values):
                actual.setdefault(int(plate), {})[group] = Counter(v for v in values if v[0] is not None)
    with zipfile.ZipFile(package) as archive:
        charts = sum(1 for n in archive.namelist() if n.startswith('xl/charts/chart'))
    problems = []
    if charts != len(expected):
        problems.append(f'{charts} charts for {len(expected)} plates with positive OD')
    if actual != expected:
        problems.append(f'chart points differ on plates {sorted(p for p in set(actual) | set(expected) if actual.get(p) != expected.get(p))}')
    wrong = {p: (lines.get(p, 0), n) for p, n in events.items() if p in expected and lines.get(p, 0) != n}
    if wrong:
        problems.append(f'propagation lines (chart, overview): {wrong}')
    return problems, charts, sum(len(g) for plate in expected.values() for g in plate.values())


def run(args):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, checks=[], command='uv run --locked python backend/e2e/plate_export_check.py', experiments={})
    upstream_python = args.upstream / '.venv/Scripts/python.exe'
    try:
        result['upstream'] = subprocess.run(['git', '-C', str(args.upstream), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
        result['code'] = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
        with sql_fixture(args.source_database) as fixture, tempfile.TemporaryDirectory(prefix='rc-plate-export-') as temporary:
            temporary = Path(temporary)
            result['fixture'] = dict(database=fixture['database'], copied_from=args.source_database, objects=[*TABLES, 'Descendants'])
            connection = (f"DRIVER={{ODBC Driver 17 for SQL Server}};SERVER={SERVER};DATABASE={fixture['database']};"
                          f"UID={fixture['login']};PWD={fixture['password']};TrustServerCertificate=yes")
            with pyodbc.connect(connection) as conn:
                all_ids = [r[0] for r in conn.execute('SELECT ExperimentID FROM dbo.Experiments').fetchall()]
            experiments = args.experiment or sorted(all_ids, reverse=True)

            started = time.monotonic()
            reference = subprocess.run([str(upstream_python), '-c', REFERENCE, connection, str(temporary/'reference'), json.dumps(experiments)],
                                       capture_output=True, text=True, env={'PYTHONPATH': str(args.upstream/'src'), 'SYSTEMROOT': 'C:\\Windows'})
            assert reference.returncode == 0, reference.stderr
            reference = {int(k): v for k, v in json.loads(reference.stdout.strip().splitlines()[-1]).items()}
            result['checks'].append(f'Desktop export (upstream export_plates) for {len(experiments)} experiments in {time.monotonic() - started:.0f} s')

            zip_path = temporary/'plate-data-export.zip'
            built = subprocess.run([sys.executable, str(ROOT/'build_scripts/database_package.py'), 'build', str(PACKAGE), '--output', str(zip_path)],
                                   capture_output=True, text=True)
            assert built.returncode == 0, built.stderr
            defaults = temporary/'no-starters'; defaults.mkdir()
            service = DatabaseTools(temporary/'tools', defaults, database=object())
            app = FastAPI(); app.include_router(router)
            def user(request: Request):
                if not request.headers.get('authorization'): raise HTTPException(401)
                return {'username': 'admin', 'role': 'admin'}
            app.dependency_overrides[get_current_user] = user
            app.dependency_overrides[get_database_tools] = lambda: service
            with TestClient(app, client=('127.0.0.1', 1234), headers={'authorization': 'admin'}) as client:
                def call(method, path, payload=None, status=200, **kwargs):
                    r = client.request(method, BASE+path, json=payload, **kwargs)
                    assert r.status_code == status, (path, r.status_code, r.text)
                    return r.json() if 'application/json' in r.headers.get('content-type', '') else r.content
                installed = call('POST', '/packages', files={'file': ('plate-data-export.zip', zip_path.read_bytes())}, data={'expected_current': 'absent'})
                assert installed['id'] == 'plate-data-export' and installed['version'] == '1.0.0', installed
                call('POST', '/sources', dict(id='primary', name='EvoYeast copy', server=SERVER, database=fixture['database'],
                                              username=fixture['login'], password=fixture['password'], trust_certificate=True))
                call('PUT', '/packages/plate-data-export/sources', dict(mappings={'primary': 'primary'}))
                result['checks'].append('Built ZIP installed through the API; SELECT-only SQL Server connection assigned')
                choices = call('POST', '/reports/plate-data-export/choices/experiment_id', dict(inputs={}))
                assert [c['value'] for c in choices['options']] == sorted(all_ids, reverse=True)[:len(choices['options'])], choices
                result['checks'].append('Experiment choices newest first (value_desc)')

                def wait(job):
                    deadline = time.monotonic() + 300
                    while job['status'] in {'pending', 'running'}:
                        assert time.monotonic() < deadline, job
                        time.sleep(.2); job = call('GET', '/reports/'+job['id'])
                    return job
                kept = None
                for experiment_id in experiments:
                    job = wait(call('POST', '/reports/plate-data-export', dict(inputs={'experiment_id': experiment_id})))
                    if reference[experiment_id] is None:
                        assert job['status'] == 'error' and job['error'] == 'This experiment has no plates to export.', job
                        result['experiments'][experiment_id] = 'no plates: short message'
                        continue
                    assert job['status'] == 'ready', job
                    path = temporary/f'package-{experiment_id}.xlsx'
                    path.write_bytes(call('GET', '/reports/'+job['id']+'/download'))
                    problems = compare(reference[experiment_id], path)
                    chart_problems, charts, points = chart_points(reference[experiment_id], path)
                    plates = openpyxl.load_workbook(path)['Overview'].max_row - 1
                    result['experiments'][experiment_id] = dict(plates=plates, charts=charts, chart_points=points,
                                                                problems=problems + chart_problems)
                    if not kept or plates > kept[1]:
                        kept = (experiment_id, plates, path)
                failed = {k: v for k, v in result['experiments'].items() if isinstance(v, dict) and v['problems']}
                assert not failed, json.dumps(failed, indent=2, default=str)
                compared = [v for v in result['experiments'].values() if isinstance(v, dict)]
                result['checks'].append(f"{len(compared)} experiments, {sum(v['plates'] for v in compared)} plates: every sheet's cell values equal the desktop export")
                result['checks'].append(f"{sum(v['charts'] for v in compared)} charts plot exactly the desktop figure's {sum(v['chart_points'] for v in compared)} positive OD points, grouped by propagation, with one line per propagation event")
                (EVIDENCE/f'plate-data-export-{kept[0]}.xlsx').write_bytes(kept[2].read_bytes())
                job_folders = [p for p in (temporary/'tools').rglob('*_plots')]
                assert not job_folders, job_folders
                result['checks'].append('No PNG folder written by the package')
        result['passed'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    (EVIDENCE/'result.json').write_text(json.dumps(result, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'experiments'}, indent=2, default=str))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--upstream', type=Path, default=Path('C:/Users/Hamilton/Desktop/Shou_LHR_PythonPackage'))
    parser.add_argument('--source-database', default='EvoYeast')
    parser.add_argument('--experiment', type=int, action='append')
    raise SystemExit(run(parser.parse_args()))
