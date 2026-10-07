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
- The ranking or growth charts differ from what the desktop figure's panels receive (recorded by
  wrapping upstream's _ranking, _growth and event_summary): a bar missing, out of robot-rank order,
  with another OD or in the wrong propagated group; the cutoff not after the robot's top N (or drawn
  when the check is N/A); crosses on the wrong bars; a growth point moved or in the wrong group; a
  summary line (or "No propagation recorded ...") different; a propagation without its two charts.
- The Experiment list is not newest first; an experiment without plates fails with a raw error
  instead of a short message.
- The output folder keeps upstream's PNG folder beside the workbook.
- A Chart data column is not referenced by any chart.
- A chart plot leaves varyColors unset: Excel then lists every point of a one-series chart in the
  legend and colours each point (seen on a plate with no propagation yet, 2026-10-07).
Not covered: chart appearance and layout (inspect a workbook in Excel), that a column is drawn by
the right chart (columns are matched by their labels), the lab's SQL Server version and data.
"""
from contextlib import contextmanager
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import zipfile

import openpyxl
from openpyxl.utils import get_column_letter
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
import json, math, sys
from pathlib import Path
import pyodbc
from hamilton_workflows import plate_export, plate_report
connection_string, out, experiments = sys.argv[1], Path(sys.argv[2]), json.loads(sys.argv[3])
result = {}

# Record what plate_figure hands its ranking and growth panels, and its summary lines, while
# export_plates draws the desktop figure: {plate: {"events": [...]}}, saved beside the workbook.
panels, current = {}, {}
figure, ranking, growth, summary = (plate_report.plate_figure, plate_report._ranking,
                                    plate_report._growth, plate_report.event_summary)
def number(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)
def record_figure(plate):
    current["plate"] = panels.setdefault(str(int(plate.plate["PlateID"])), {"events": []})
    return figure(plate)
def record_summary(event):
    text = summary(event)
    current["plate"]["events"].append({"summary": text})
    return text
def record_ranking(ax, rows, event):
    rows = rows.sort_values("RobotRank")  # as _ranking
    checked = event.RankingCheck != "N/A"
    current["plate"]["events"][-1].update(
        ranking=[[r.Well, number(r.OD), bool(r.Selected)] for r in rows.itertuples()],
        cutoff=int(event.Expected) if checked else None,
        disagrees=[i for i, m in enumerate(rows["Match"], 1) if not bool(m)] if checked else [])
    return ranking(ax, rows, event)
def record_growth(ax, rows):
    current["plate"]["events"][-1]["growth"] = {
        str(selected): [[number(r.OD), number(r.GrowthRate)] for r in rows[rows["Selected"] == selected].itertuples()]
        for selected in (False, True)}
    return growth(ax, rows)
plate_report.plate_figure, plate_report._ranking = record_figure, record_ranking
plate_report._growth, plate_report.event_summary = record_growth, record_summary

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
        panels.clear()
        result[experiment_id] = str(plate_report.export_plates(data, ids, folder))
        (folder / "panels.json").write_text(json.dumps(panels))
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
    """Cell-value differences between the desktop and package workbooks (charts/images ignored).

    Returns (problems, lines): below its table a package plate sheet has text lines in column A
    (the figure's summary lines); ``lines`` maps plate to them for panel_points to check.
    """
    expected, actual = openpyxl.load_workbook(reference), openpyxl.load_workbook(package)
    names = [n for n in actual.sheetnames if n != CHART_DATA]
    problems = [] if expected.sheetnames == names else [f'sheets {expected.sheetnames} != {names}']
    lines = {}
    for name in set(expected.sheetnames) & set(names):
        want, got = sheet_values(expected, name), sheet_values(actual, name)
        extra = [r for r in got[len(want):] if any(v is not None for v in r)]
        if name.isdigit():
            lines[int(name)] = [r[0] for r in extra]
            extra = [r for r in extra if any(v is not None for v in r[1:])]
        if len(want) > len(got) or extra:
            problems.append(f'{name}: {len(want)} rows, package {len(got)}')
        for row, (a, b) in enumerate(zip(want, got), 1):
            if a != b:
                problems.append(f'{name} row {row}: {a} != {b}')
                break
    return problems, lines


def panel_points(reference, package, lines):
    """The package's ranking and growth charts against what the desktop figure's panels received.

    ``reference`` is the panels.json recorded from upstream's plate_figure. Per propagation: the
    bars (well, OD) in robot-rank order and their propagated/not split, the cutoff (top N) and the
    crosses where the rule disagrees, the growth points per group, and the summary line.
    """
    # openpyxl stores a float as '%.16g' (openpyxl.compat.strings.safe_string), so compare with
    # that stored value, exactly as any workbook (the desktop one included) holds it.
    stored = lambda v: float('%.16g' % v) if isinstance(v, float) else v
    figure = {int(p): v['events'] for p, v in json.loads(Path(reference).read_text(),
                                                         parse_float=lambda s: stored(float(s))).items()}
    book = openpyxl.load_workbook(package)
    data = book[CHART_DATA] if CHART_DATA in book.sheetnames else None  # absent when nothing is charted
    columns = {data.cell(1, c).value: [data.cell(r, c).value for r in range(2, data.max_row + 1)]
               for c in range(1, data.max_column + 1)} if data else {}
    def column(header):
        values = columns.get(header, [])
        while values and values[-1] is None:
            values = values[:-1]
        return values
    problems = []
    for plate, events in figure.items():
        want = [e['summary'] for e in events] or ['No propagation recorded from this plate yet']
        if lines.get(plate) != want:
            problems.append(f'plate {plate} lines {lines.get(plate)} != {want}')
        for number, event in enumerate(events, 1):
            label = f'Plate {plate} propagation {number}'
            bars = event['ranking']
            ranking = (column(f'{label} ranking well'), column(f'{label} ranking Propagated OD'),
                       column(f'{label} ranking Not propagated OD'))
            want = ([w for w, _, _ in bars], [od if s else None for _, od, s in bars],
                    [None if s else od for _, od, s in bars])
            got = list(zip(*[list(c) + [None] * (len(bars) - len(c)) for c in ranking]))
            if got != list(zip(*want)):
                first = next(((g, w) for g, w in zip(got + [None] * len(bars), zip(*want)) if g != w), (got, []))
                problems.append(f'{label}: ranking bars differ, first (well, propagated OD, not propagated OD) {first[0]} != figure {first[1]}')
            cutoff = event['cutoff']
            if column(f'{label} ranking cutoff x') != ([cutoff + 0.5] * 2 if cutoff is not None else []):
                problems.append(f'{label}: cutoff {column(f"{label} ranking cutoff x")}, figure top {cutoff}')
            if column(f'{label} ranking disagrees x') != event['disagrees']:
                problems.append(f'{label}: disagreeing bars {column(f"{label} ranking disagrees x")} != {event["disagrees"]}')
            for selected, name in (('True', 'Propagated'), ('False', 'Not propagated')):
                points = event['growth'][selected]
                got = list(zip(column(f'{label} growth {name} OD'), column(f'{label} growth {name} rate') + [None] * len(points)))
                want = [tuple(p) for p in points]
                if got != want:
                    first = next(((g, w) for g, w in zip(got + [None] * len(want), want + [None] * len(got)) if g != w))
                    problems.append(f'{label}: {name} growth points differ, first (OD, rate) {first[0]} != figure {first[1]}')
    return problems, sum(len(e) for e in figure.values()), sum(len(e['ranking']) for es in figure.values() for e in es)


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
        for column in range(1, data.max_column + 1):
            label = data.cell(1, column).value
            if not label.endswith(' hours'):  # the time course's (hours, OD) pairs; panel_points reads the rest
                continue
            plate, group = label.removeprefix('Plate ').removesuffix(' hours').split(' ', 1)
            values = [(data.cell(r, column).value, data.cell(r, column + 1).value) for r in range(2, data.max_row + 1)]
            if group == 'Propagation':
                runs = sum(1 for i, v in enumerate(values) if v[0] is not None and (i == 0 or values[i - 1][0] is None))
                lines[int(plate)] = runs
            elif any(x is not None for x, _ in values):
                actual.setdefault(int(plate), {})[group] = Counter(v for v in values if v[0] is not None)
    with zipfile.ZipFile(package) as archive:
        xml = [archive.read(n).decode() for n in archive.namelist() if n.startswith('xl/charts/chart')]
    charts = len(xml)
    problems = []
    # Excel treats a missing varyColors as on, so a one-series chart (no propagation yet) lists
    # every point in the legend and colours each one; the fixture's plates all have two series.
    varied = sum(1 for x in xml for plot in re.findall(r'<(?:\w+:)?(?:scatter|bar)Chart>(.*?)</(?:\w+:)?(?:scatter|bar)Chart>', x, re.S)
                 if not re.search(r'<(?:\w+:)?varyColors val="0"', plot))
    if varied:
        problems.append(f'{varied} chart plot(s) without varyColors="0" (Excel varies colours per point)')
    # Every Chart data column holding values is drawn: some chart's series refers to it.
    drawn = {c for x in xml for c in re.findall(r"'Chart data'!\$([A-Z]+)\$2", x)}
    if CHART_DATA in book.sheetnames:
        data = book[CHART_DATA]
        undrawn = [h.value for h in data[1] if get_column_letter(h.column) not in drawn
                   and any(data.cell(r, h.column).value is not None for r in range(2, data.max_row + 1))]
        if undrawn:
            problems.append(f'chart data not drawn by any chart: {undrawn[:5]}')
    if charts != len(expected) + 2 * sum(events.values()):
        problems.append(f'{charts} charts for {len(expected)} plates with positive OD and {sum(events.values())} propagations')
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
                assert installed['id'] == 'plate-data-export' and installed['version'] == json.loads((PACKAGE / 'manifest.json').read_text(encoding='utf-8'))['version'], installed
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
                    problems, lines = compare(reference[experiment_id], path)
                    chart_problems, charts, points = chart_points(reference[experiment_id], path)
                    panel_problems, events, bars = panel_points(Path(reference[experiment_id]).parent/'panels.json', path, lines)
                    plates = openpyxl.load_workbook(path)['Overview'].max_row - 1
                    result['experiments'][experiment_id] = dict(plates=plates, charts=charts, chart_points=points,
                                                                propagations=events, bars=bars,
                                                                problems=problems + chart_problems + panel_problems)
                    if not kept or plates > kept[1]:
                        kept = (experiment_id, plates, path)
                failed = {k: v for k, v in result['experiments'].items() if isinstance(v, dict) and v['problems']}
                assert not failed, json.dumps(failed, indent=2, default=str)
                compared = [v for v in result['experiments'].values() if isinstance(v, dict)]
                result['checks'].append(f"{len(compared)} experiments, {sum(v['plates'] for v in compared)} plates: every sheet's cell values equal the desktop export")
                result['checks'].append(f"{sum(v['charts'] for v in compared)} charts (time course per plate with positive OD, ranking and growth per propagation)")
                result['checks'].append(f"Time courses plot exactly the desktop figure's {sum(v['chart_points'] for v in compared)} positive OD points, grouped by propagation, with one line per propagation event")
                result['checks'].append(f"{sum(v['propagations'] for v in compared)} propagations: ranking charts draw the figure's {sum(v['bars'] for v in compared)} bars in robot-rank order with its propagated split, cutoff and disagreements; growth charts its points; summary lines (or 'No propagation') equal the figure's")
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
