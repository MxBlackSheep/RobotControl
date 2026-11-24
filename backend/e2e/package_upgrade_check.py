"""V1.0.0b1 package upgrade and version eligibility; no instrument launch.

Run: uv run --locked python -m backend.e2e.package_upgrade_check
Needs Git object 886cdf5, backend dependencies and sql_fixture prerequisites.
Only disposable SQL/SQLite data are used. VENUS commands and PyHSL HTTP are stubbed.

Accepted interface: packages payload and PackageCatalogue.compatibility(manifest)
return state ('ready', 'needs_review', 'needs_newer') and reason. Missing minimum
means needs_review; a satisfied minimum means ready; an unmet minimum means
needs_newer. Consumer refusals carry that same reason (existing preparation
wrappers may prefix it). No approval API, records, recognition or index migration.

Plan / failure cases:
1. Load b1 catalogue/service AND starter files from Git; create real version-2
   index, connection bindings, schedule pins, pending confirmation and receipt.
2. Open twice with a service restart: assert unchanged entries, files, history,
   connections and schedules; all undeclared entries visible as needs_review.
   This state assertion precedes new-interface calls, so 428ba6e fails an assertion,
   not fixture setup or a missing method/key. No approval is inherited.
3. Exercise reserve, worker entry, preview/execute, lookups, Champions, Open
   Scheduling/pinning, unchanged schedule arming, preparation readiness/execution
   and both scheduler launchers. Recovery, export, history and removal still work.
4. Import declared copies; exercise reports, operations, experiment registration,
   scheduling handoff and preparation through both scheduler launchers. Old pins
   remain unchanged and need explicit repinning because import changes the hash.
5. A declared sibling runs while its neighbours are blocked. Too-new imports
   (b2 and final) refuse atomically; copies installed on a newer version remain
   visible but refuse all the same boundaries after restart on b1.

Report/delete use the existing SQLite adapter; registration/preparation use the
SQL Server fixture. This does not certify laboratory stored procedures or UI.
"""
from contextlib import closing, nullcontext
import copy
from datetime import datetime, timedelta
import hashlib
import io
import zipfile
import threading
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import patch, Mock
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from backend.api.database_tools import router
from backend.e2e.database_fixture import (
    DatabaseFixture, configure_fixture_report_sources,
)
from backend.e2e.experiment_registration_check import TABLES, archive, incubation_manifest
from backend.e2e.sql_server_fixture import sql_fixture
from packaging.version import Version
from backend import version
from backend.models import ScheduledExperiment, JobExecution
from backend.services.auth import get_current_user
from backend.services.database_packages import PackageError
from backend.services.database_tools import DatabaseTools, PreparationFailed, get_database_tools
from backend.services.report_sources import ReportSource, ReportSources
from backend.services.scheduling.pre_execution import PreExecutionPipeline
from backend.services.scheduling.sqlite_database import SQLiteSchedulingDatabase

ROOT = Path(__file__).resolve().parents[2]
BASE = '/api/database/tools'
B1 = '886cdf5'
STARTERS = {'champions-experiment', 'culture-history', 'delete-experiment',
            'evoyeast-experiment', 'plate-data-export'}


def b1_module(filename):
    name = 'backend.services._upgrade_check_b1_' + Path(filename).stem
    module = ModuleType(name)
    module.__file__ = str(ROOT / filename)
    sys.modules[name] = module  # Pydantic resolves annotations through this module.
    source = subprocess.check_output(['git', 'show', f'{B1}:{filename}'], cwd=ROOT)
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


def app_for(service):
    app = FastAPI()
    app.include_router(router)

    def user(request: Request):
        name = request.headers.get('authorization')
        if not name:
            raise HTTPException(401)
        return dict(username=name, role='user' if name == 'user' else 'admin')

    app.dependency_overrides[get_current_user] = user
    app.dependency_overrides[get_database_tools] = lambda: service
    return app


def seed_b1(root, defaults, fixture, writer):
    """Use b1's real seeding, connection persistence and pin creation paths."""
    old_packages = b1_module('backend/services/database_packages.py')
    old_tools = b1_module('backend/services/database_tools.py')
    old_tools.PackageCatalogue = old_packages.PackageCatalogue
    old_tools.log_action = lambda **kwargs: None
    service = old_tools.DatabaseTools(root, defaults, guard=nullcontext)
    service.catalogue.in_use = lambda _: []
    storage = SQLiteSchedulingDatabase(str(root / 'scheduler.db'))
    try:
        for name, access in [('reader', 'read'), ('writer', 'operation')]:
            service.sources.save(ReportSource(
                id=name, name=name, server=fixture['server'], database=fixture['names'][0],
                username=writer if access == 'operation' else fixture['login'], password=fixture['password'],
                trust_certificate=True, access=access))
        for package_id, entry in service.catalogue.index.items():
            aliases = service.sources.aliases(entry['manifest'])
            service.sources.bind(package_id, aliases, {alias: 'reader' for alias in aliases})
            if any(t['kind'] in ('operation', 'preparation') for t in entry['manifest']['tools']):
                service.sources.bind_operation(package_id, 'writer')
        service.sources.bind_operation('experiments', 'writer')
        pin = service.pin_preparation('evoyeast-experiment', {'experiment_id': 1}, 'existing-admin')
        for runner in ('venus', 'pyhsl'):
            schedule = ScheduledExperiment(
                schedule_id=runner, experiment_name='Upgrade ' + runner,
                experiment_path='fixture.med' if runner == 'venus' else 'fixture-protocol',
                schedule_type='once', start_time=datetime.now() + timedelta(days=1),
                mode='simulation', runner=runner, is_active=False, preparation=copy.deepcopy(pin),
                protocol_id='fixture-protocol' if runner == 'pyhsl' else None,
                protocol_revision='b1-protocol-revision' if runner == 'pyhsl' else None,
                parameters={'ExperimentID': 1} if runner == 'pyhsl' else {})
            assert storage.create_schedule(schedule)
        # A non-starter has the same undeclared state as the bundled packages.
        value = incubation_manifest()
        value.pop('min_robotcontrol_version', None)
        service.catalogue.install(archive(value), actor='existing-admin')
        inputs = registration_inputs(service, 'champions-experiment')
        token = uuid.uuid4().hex
        receipt = service.register_experiment(token, inputs, 'admin', None)
        assert receipt['status'] == 'succeeded', receipt
        # An actual b1 preview, retained across the service restart for execute refusal.
        original_sources = service.sources
        import backend.services.report_worker as worker
        with patch.object(worker, 'run_report', worker.run_report):
            service.sources = ReportSources(root)
            try:
                configure_fixture_report_sources(service, DatabaseFixture(root))
                preview = service.preview('delete-experiment', {'experiment_id': 43}, 'admin')
                pending = copy.deepcopy(service.previews[preview['token']])
            finally:
                service.sources = original_sources
        index = json.loads(service.catalogue.index_path.read_text('utf-8'))
        assert index['version'] == 2 and set(index['packages']) == STARTERS | {'incubation-check'}
        assert all('approval' not in e for e in index['packages'].values())
        return (index, {r: storage.get_schedule_by_id(r).to_dict() for r in ('venus', 'pyhsl')},
                pending, (token, inputs, receipt))
    finally:
        service.close()


def execute_kinds(service, fixture, root):
    # Use the established SQLite report/delete adapter only during those workflows.
    # Its worker delegates to production run_report in the spawned child.
    database = DatabaseFixture(root)
    original_sources = service.sources
    import backend.services.report_worker as worker
    with patch.object(worker, 'run_report', worker.run_report):
        service.sources = ReportSources(service.root)
        try:
            configure_fixture_report_sources(service, database)
            job = service.start_report('culture-history', {'experiment_id': 42}, 'admin')
            deadline = time.monotonic() + 60
            while job['status'] in ('pending', 'running') and time.monotonic() < deadline:
                time.sleep(0.1)
                job = service.report(job['id'], 'admin')
            assert job['status'] == 'ready', job
            assert service.download(job['id'], 'admin').is_file()
            preview = service.preview('delete-experiment', {'experiment_id': 43}, 'admin')
            result = service.execute(preview['token'], preview['confirmation'], 'admin', None)
            assert result['status'] == 'succeeded', result
            with closing(sqlite3.connect(database.path)) as conn:
                assert conn.execute('SELECT 1 FROM Experiments WHERE ExperimentID=43').fetchone() is None
        finally:
            service.sources = original_sources

    storage = SQLiteSchedulingDatabase(str(service.root / 'scheduler.db'))
    for runner in ('venus', 'pyhsl'):
        schedule = storage.get_schedule_by_id(runner)
        # Import changes the archive hash: explicitly save a new pin, never migrate it.
        schedule.preparation = service.pin_preparation('evoyeast-experiment', {'experiment_id': 1}, 'admin')
        assert service.preparation_state(schedule.preparation) == 'ready'
        assert storage.update_schedule(schedule)
    scheduler_paths(service, None)
    rows = fixture['admin'].execute('SELECT ExperimentID FROM Experiments WHERE ScheduledToRun=1').fetchall()
    assert [r[0] for r in rows] == [1]

    definition = next(t for t in service.experiment_types() if t['id'] == 'champions-experiment')
    inputs = dict(type_id=definition['id'], package_version=definition['package_version'],
                  sha256=definition['sha256'], user_defined_id=uuid.uuid4().hex, note='', schedule=0,
                  parameters={p['name']: p['default'] for p in definition['parameters']},
                  layout=definition['layout']['default'])
    token = uuid.uuid4().hex
    result = service.register_experiment(token, inputs, 'admin', None)
    assert result['status'] == 'succeeded', result
    experiment_id = result['result']['experiment_id']
    admin = fixture['admin']
    assert admin.execute('SELECT COUNT(*) FROM ExperimentParameters WHERE ExperimentID=?', experiment_id).fetchone()[0] == len(inputs['parameters'])
    assert admin.execute('SELECT COUNT(*) FROM ExperimentPlatePattern WHERE ExperimentID=?', experiment_id).fetchone()[0] == len(inputs['layout'])

    draft = service.experiment_schedule_draft(experiment_id, token, 'admin')
    pin = service.pin_preparation(draft['tool_id'], draft['inputs'], 'admin', draft['expected_origin'])
    assert service.preparation_state(pin) == 'ready'


def registration_inputs(service, tool_id):
    definition = next(t for t in service.experiment_types() if t['id'] == tool_id)
    return dict(type_id=tool_id, package_version=definition['package_version'],
                sha256=definition['sha256'], user_defined_id=uuid.uuid4().hex, note='', schedule=0,
                parameters={p['name']: p['default'] for p in definition['parameters']},
                layout=(definition.get('layout') or {}).get('default'))


def git_defaults(destination):
    """Never seed b1 from the concurrently edited working-tree manifests."""
    files = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', B1,
                                     '--', 'database_packages'], cwd=ROOT, text=True).splitlines()
    for name in files:
        relative = Path(name).relative_to('database_packages')
        if relative.parts[0] not in STARTERS:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(['git', 'show', f'{B1}:{name}'], cwd=ROOT))
    for manifest in destination.glob('*/manifest.json'):
        assert 'min_robotcontrol_version' not in json.loads(manifest.read_text('utf-8'))


def files_under(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def declared_copy(content, minimum):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source, zipfile.ZipFile(output, 'w') as target:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename == 'manifest.json':
                value = json.loads(data)
                value['min_robotcontrol_version'] = minimum
                data = json.dumps(value).encode()
            target.writestr(member, data)
    return output.getvalue()


def states(service, expected, ids):
    with TestClient(app_for(service), client=('127.0.0.1', 1234),
                    headers={'authorization': 'admin'}) as client:
        response = client.get(BASE + '/packages')
        assert response.status_code == 200, response.text
        rows = {row['id']: row for row in response.json()}
    reasons = {}
    for key in ids:
        row = rows[key]
        # Deliberate first failure on 428ba6e: no new API call or indexing absent keys.
        assert row.get('state') == expected, (key, expected, row)
        reason = row.get('reason')
        if expected == 'needs_review':
            assert isinstance(reason, str) and 'import a copy' in reason.lower() and 'declares min_robotcontrol_version' in reason, row
        elif expected == 'needs_newer':
            minimum = service.catalogue.index[key]['manifest']['min_robotcontrol_version']
            assert reason == f'Requires RobotControl {minimum} or later. This computer has {version.__version__}.', row
        else:
            assert not reason, row
        compatibility = service.catalogue.compatibility(service.catalogue.index[key]['manifest'])
        assert compatibility['state'] == expected and compatibility['reason'] == reason
        reasons[key] = reason
    return reasons


def assert_continuity(service, original, schedules, source_bytes, package_files):
    assert service.catalogue.index == original['packages']
    assert json.loads(service.catalogue.index_path.read_text('utf-8')) == original
    assert original['version'] == 2
    assert files_under(service.catalogue.root) == package_files
    assert service.sources.path.read_bytes() == source_bytes
    storage = SQLiteSchedulingDatabase(str(service.root / 'scheduler.db'))
    for runner, saved in schedules.items():
        assert storage.get_schedule_by_id(runner).to_dict() == saved
    for key, before in original['packages'].items():
        content, _ = service.catalogue.export(key)
        assert hashlib.sha256(content).hexdigest() == before['sha256']
        assert service.catalogue.history(key) == list(reversed(before.get('history', [])))
        assert 'approval' not in service.catalogue.index[key]


def refused(call, reason, *, wrapped=False):
    from backend.services.sqlite_safety import SafetyConflict
    try:
        result = call()
    except (PackageError, PreparationFailed, SafetyConflict) as exc:
        if isinstance(exc, PackageError):
            assert exc.status == 409, exc
        message = str(exc)
    else:
        assert isinstance(result, dict) and result.get('status') == 'error', result
        message = result.get('message', '')
    assert (reason in message if wrapped else reason == message), (reason, message)


def scheduler_paths(service, reason):
    """Real launcher control flow, fake final commands/HTTP, real preparation pipeline."""
    from backend.services.scheduling.experiment_executor import ExecutionConfig, ExecutionResult, ExperimentExecutor
    from backend.services.scheduling.pyhsl_runner import PyHslRunner
    storage = SQLiteSchedulingDatabase(str(service.root / 'scheduler.db'))
    manager = SimpleNamespace(sqlite_db=storage)
    with patch('backend.services.database_tools.get_database_tools', return_value=service):
        schedule = storage.get_schedule_by_id('venus')
        execution = JobExecution(uuid.uuid4().hex, schedule.schedule_id, 'running')
        with patch('backend.services.scheduling.experiment_executor.get_scheduling_database_manager', return_value=manager):
            executor = ExperimentExecutor(SimpleNamespace(check=lambda _: SimpleNamespace(run_state='Complete')),
                                          lambda *args: nullcontext(), ExecutionConfig(hxrun_path='not-a-robot.exe'))
        executions = [(execution.execution_id, schedule.preparation)]
        command = Mock(return_value=ExecutionResult(True, 0, '', '', 0, 'fixture-command'))
        with patch.object(executor, '_execute_real_command', command), patch(
                'backend.services.scheduling.experiment_executor.get_experiment_discovery_service',
                return_value=SimpleNamespace(db=SimpleNamespace(update_method_usage=lambda _: None))):
            ok = executor.execute_experiment(schedule, execution)
        assert ok == (reason is None), execution.error_message
        if reason:
            assert execution.error_message == reason
            command.assert_not_called()
        else:
            command.assert_called_once()

        schedule = storage.get_schedule_by_id('pyhsl')
        engine = SimpleNamespace(db_manager=manager, _running=True, launch_guard=lambda *args: nullcontext())
        # Stub the transport at construction: even an incorrectly admitted run stays local.
        client = Mock()
        def post(path, *args, **kwargs):
            if path == '/validate':
                return {'protocol': {'revision': schedule.protocol_revision}}
            assert path == '/runs', path
            return {'run_id': 'fixture-run'}
        client.post.side_effect = post
        client.get.side_effect = lambda path, **kwargs: (
            {'status': 'completed'} if path.startswith('/runs/') else
            {'active': False, 'blocked': False, 'cases': []})
        with patch('backend.services.pyhsl_client.PyHslClient', return_value=client):
            runner = PyHslRunner(engine)
        # Receipt persistence/finalization are not the eligibility boundary.
        with patch.object(runner, '_save'), patch.object(runner, '_finish') as finish:
            execution = JobExecution(uuid.uuid4().hex, schedule.schedule_id, 'pending')
            executions.append((execution.execution_id, schedule.preparation))
            runner.execute(schedule, execution)
            args = finish.call_args
            assert args is not None, 'PyHSL path did not finish'
            assert args.args[2] == ('failed' if reason else 'completed'), args
            if reason:
                assert args.args[3] == reason, args
            starts = [call for call in client.post.call_args_list if call.args[0] == '/runs']
            assert len(starts) == (0 if reason else 1), starts
            # Already dispatched runs must still be followed even with blocked preparation.
            client.reset_mock()
            finish.reset_mock()
            execution.status = 'running'
            execution.pyhsl = {'run_id': 'existing-run'}
            runner.execute(schedule, execution)
            assert finish.call_args.args[2] == 'completed', finish.call_args
            client.post.assert_not_called()
            client.get.assert_any_call('/runs/existing-run')
        with storage._get_connection() as conn:
            for execution_id, pin in executions:
                row = conn.execute('SELECT status, package FROM LabPreparation WHERE execution_id=?',
                                   (execution_id,)).fetchone()
                if reason is None:
                    assert row and row['status'] == 'prepared' and json.loads(row['package']) == pin, row
                else:
                    assert row is None, 'Blocked preparation created an attempt receipt'


def arming_refuses(service, reason):
    from backend.api import scheduling as api
    storage = SQLiteSchedulingDatabase(str(service.root / 'scheduler.db'))
    scheduler = SimpleNamespace(get_schedule=storage.get_schedule_by_id, _schedules_lock=threading.RLock(),
        update_schedule=Mock(side_effect=AssertionError('Blocked schedule must not be armed')))
    app = app_for(service)
    app.include_router(api.router)
    with patch.object(api, 'log_action'), patch.object(api, 'get_services', return_value=(scheduler, storage, None)), patch(
            'backend.services.database_tools.get_database_tools', return_value=service), TestClient(
            app, client=('127.0.0.1', 1234), headers={'authorization': 'admin'}) as client:
        for key in ('venus', 'pyhsl'):
            schedule = storage.get_schedule_by_id(key)
            response = client.put('/api/scheduling/' + key, json={
                'is_active': True, 'expected_updated_at': schedule.updated_at.isoformat()})
            assert response.status_code == 409 and response.json()['detail'] == reason, response.text
            assert storage.get_schedule_by_id(key).to_dict() == schedule.to_dict()
    scheduler.update_schedule.assert_not_called()


def blocked_paths(service, reasons, pending, receipt):
    from backend.services import report_worker
    for key, reason in reasons.items():
        entry = service.catalogue.index[key]
        for tool in entry['manifest']['tools']:
            def reserve():
                with service.catalogue.reserve(tool['id'], tool['kind']):
                    raise AssertionError('Blocked package reserved: ' + key)
            refused(reserve, reason)
            if tool['kind'] in ('report', 'preparation'):
                messages = []
                channel = SimpleNamespace(send=messages.append, close=lambda: None)
                with patch.object(report_worker, '_runtime', side_effect=AssertionError('Worker opened runtime')):
                    if tool['kind'] == 'report':
                        report_worker.run_report(channel, str(service.catalogue.root), entry, tool, {}, {}, str(service.temp))
                    else:
                        report_worker.run_preparation(channel, str(service.catalogue.root), entry, tool, {}, {}, {}, {})
                assert messages == [{'error': reason, **({'expected': True} if tool['kind'] == 'report' else {})}], messages
    for tool_id in ('culture-history', 'plate-data-export'):
        refused(lambda: service.start_report(tool_id, {'experiment_id': 42}, 'admin'), reasons[tool_id])
    refused(lambda: service.preview('delete-experiment', {'experiment_id': 43}, 'admin'), reasons['delete-experiment'])
    token = uuid.uuid4().hex
    service.previews[token] = {**copy.deepcopy(pending), 'expires': time.time() + 600}
    refused(lambda: service.execute(token, '43', 'admin', None), reasons['delete-experiment'])
    for tool_id, kind in [('culture-history', 'report'), ('plate-data-export', 'report'),
                          ('delete-experiment', 'operation'), ('evoyeast-experiment', 'preparation')]:
        refused(lambda: service.choices(tool_id, 'experiment_id', {}, '', 0, kind=kind), reasons[tool_id])
    refused(lambda: service.register_experiment(uuid.uuid4().hex, registration_inputs(service, 'champions-experiment'), 'admin', None), reasons['champions-experiment'])
    old_token, inputs, saved = receipt
    assert service.register_experiment(old_token, inputs, 'admin', None) == saved
    refused(lambda: service.experiment_schedule_draft(saved['result']['experiment_id'], old_token, 'admin'), reasons['evoyeast-experiment'])
    refused(lambda: service.pin_preparation('evoyeast-experiment', {'experiment_id': 1}, 'admin'), reasons['evoyeast-experiment'])
    storage = SQLiteSchedulingDatabase(str(service.root / 'scheduler.db'))
    pin = storage.get_schedule_by_id('venus').preparation
    state, reason = service.preparation_review(pin)
    assert state != 'ready' and reason == reasons['evoyeast-experiment'], (state, reason)
    refused(lambda: service.prepare_for_run(pin, {}), reason, wrapped=True)
    with patch('backend.services.database_tools.get_database_tools', return_value=service):
        refused(lambda: PreExecutionPipeline(SimpleNamespace(sqlite_db=storage)).prepare(
            storage.get_schedule_by_id('venus'), uuid.uuid4().hex), reason)
    arming_refuses(service, reason)
    scheduler_paths(service, reason)


def sibling_runs(service):
    states(service, 'ready', ['declared-sibling'])
    result = service.register_experiment(uuid.uuid4().hex, registration_inputs(service, 'declared-sibling'), 'admin', None)
    assert result['status'] == 'succeeded', result


def upload(service, content):
    with TestClient(app_for(service), client=('127.0.0.1', 1234), headers={'authorization': 'admin'}) as client:
        return client.post(BASE + '/packages', files={'file': ('package.zip', content)})


def main():
    assert version.__version__ == '1.0.0b1'
    assert Version('1.0.0b1') < Version('1.0.0b2') < Version('1.0.0rc1') < Version('1.0.0')
    with tempfile.TemporaryDirectory(prefix='rc-package-upgrade-') as temporary, sql_fixture() as fixture:
        root = Path(temporary)
        defaults = root / 'database_packages'
        git_defaults(defaults)
        admin = fixture['admin']
        admin.execute(f"USE [{fixture['names'][0]}]")
        for statement in TABLES.split(';'):
            if statement.strip():
                admin.execute(statement)
        admin.execute("INSERT INTO Experiments(UserDefinedID, ScheduledToRun) VALUES ('old preparation', 0), ('other', 1)")
        writer = fixture['login'] + '_writer'
        admin.execute(f"CREATE LOGIN [{writer}] WITH PASSWORD='{fixture['password']}', CHECK_POLICY=OFF")
        admin.execute(f'CREATE USER [{writer}] FOR LOGIN [{writer}]')
        admin.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE TO [{writer}]')
        with patch('backend.services.database_tools.log_action'), patch('backend.api.database_tools.log_action'):
            original, schedules, pending, receipt = seed_b1(root / 'tools', defaults, fixture, writer)
            source_bytes = (root / 'tools/report-sources.json').read_bytes()
            package_files = files_under(root / 'tools/packages')
            originals = {}
            for opening in range(2):
                service = DatabaseTools(root / 'tools', defaults, guard=nullcontext)
                try:
                    service.catalogue.in_use = lambda _: []
                    assert_continuity(service, original, schedules, source_bytes, package_files)
                    states(service, 'needs_review', original['packages'])
                    originals = {key: service.catalogue.export(key)[0] for key in original['packages']}
                finally:
                    service.close()
            service = DatabaseTools(root / 'tools', defaults, guard=nullcontext)
            try:
                service.catalogue.in_use = lambda _: []
                sibling = incubation_manifest()
                sibling.update(id='declared-sibling', min_robotcontrol_version='1.0.0b1')
                sibling['tools'][0]['id'] = 'declared-sibling'
                assert upload(service, archive(sibling)).status_code == 200
                sibling_runs(service)
                reasons = states(service, 'needs_review', originals)
                blocked_paths(service, reasons, pending, receipt)
                sibling_runs(service)
                # An ordinary undeclared upload is installed, inspectable and removable.
                value = incubation_manifest()
                value.pop('min_robotcontrol_version', None)
                value['id'] = value['tools'][0]['id'] = 'removable-package'
                response = upload(service, archive(value))
                assert response.status_code == 200, response.text
                states(service, 'needs_review', ['removable-package'])
                with TestClient(app_for(service), client=('127.0.0.1', 1234), headers={'authorization': 'admin'}) as client:
                    response = client.post(BASE + '/packages/removable-package/approve',
                                           json={'reviewed': True})
                    assert response.status_code in (404, 405), response.text
                with TestClient(app_for(service), client=('127.0.0.1', 1234), headers={'authorization': 'admin'}) as client:
                    for suffix in ('/export', '/history'):
                        response = client.get(BASE + '/packages/removable-package' + suffix)
                        assert response.status_code == 200, response.text
                    response = client.delete(BASE + '/packages/removable-package')
                    assert response.status_code == 200, response.text
                assert 'removable-package' not in service.catalogue.index
                for key, content in originals.items():
                    response = upload(service, declared_copy(content, '1.0.0b1'))
                    assert response.status_code == 200, response.text
                    states(service, 'ready', [key])
                    for tool in service.catalogue.index[key]['manifest']['tools']:
                        with service.catalogue.reserve(tool['id'], tool['kind']):
                            pass
                    sibling_runs(service)
                assert json.loads(service.catalogue.index_path.read_text('utf-8'))['version'] == 2
                assert all('approval' not in entry for entry in service.catalogue.index.values())
                # Non-starter experiment also runs after its declared reimport.
                result = service.register_experiment(uuid.uuid4().hex, registration_inputs(service, 'incubation-check'), 'admin', None)
                assert result['status'] == 'succeeded', result
                storage = SQLiteSchedulingDatabase(str(service.root / 'scheduler.db'))
                for key, saved in schedules.items():
                    assert storage.get_schedule_by_id(key).to_dict() == saved
                execute_kinds(service, fixture, root)
                for minimum in ('1.0.0b2', '1.0.0'):
                    before = files_under(service.catalogue.root)
                    for key, content in originals.items():
                        response = upload(service, declared_copy(content, minimum))
                        reason = f'Requires RobotControl {minimum} or later. This computer has 1.0.0b1.'
                        assert response.status_code == 409 and response.json()['detail'] == reason, response.text
                    assert files_under(service.catalogue.root) == before
                    # Genuine installation on a newer host, then restart on b1.
                    with patch.object(version, '__version__', minimum):
                        for content in originals.values():
                            service.catalogue.install(declared_copy(content, minimum))
                    service.close()
                    service = DatabaseTools(root / 'tools', defaults, guard=nullcontext)
                    service.catalogue.in_use = lambda _: []
                    reasons = states(service, 'needs_newer', originals)
                    sibling_runs(service)
                    blocked_paths(service, reasons, pending, receipt)
                    sibling_runs(service)
            finally:
                service.close()
    print('Package upgrade states and recovery passed; no instrument launched.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
