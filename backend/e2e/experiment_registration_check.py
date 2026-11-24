"""Installed experiment definitions through HTTP, journal and scratch SQL Server.

Run: uv run --locked python backend/e2e/experiment_registration_check.py [<Shou_LHR checkout> <Shou_Lab checkout>]
Defaults are the sibling Shou_LHR_PythonPackage and Shou_Lab checkouts. --contract-only
runs the HTTP/catalogue/refusal/replay checks without SQL. Full mode creates only
.\\HAMILTON/EvoYeast_RCDev, refuses a pre-existing database, and drops it in finally.
master is opened only to check/create/drop that scratch database; no lab database opens.

Failure cases: unknown/changed/removed definitions; strict scalar, bounds, allowed,
fixed, required-well and exact whole-count refusals; missing/extra fields; auth;
empty parent reuse, populated/ambiguous parent refusal, no-layout without pattern
storage, concurrent IDs, scheduling failure rollback and uncertain commit replay.
Scheduling handoff resolves matching read/write bindings without SQL or a schedule
write; active snapshots preserve empty, single, multiple and failed lookup states.
Eight parameter rows and pattern rows are compared with the unchanged exe source.
The shipped Champions manifest supplies the installed definition. Its manifest-only
release ZIP round-trips through install/export/history/removal; only fresh catalogues seed it.
Scratch column limits and procedure behavior do not establish lab compatibility.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager, nullcontext
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from unittest.mock import patch
import uuid
import zipfile

import pyodbc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from backend.api.database_tools import router
from backend.services.auth import get_current_user
from backend.services.database_tools import DatabaseTools, get_database_tools
from backend.services.database_packages import PackageCatalogue, PackageError, inspect_archive

DB = 'EvoYeast_RCDev'
SERVER = r'.\HAMILTON'
DRIVER = '{SQL Server Native Client 10.0}'
BASE = '/api/database/tools/experiments'
TABLES = """
CREATE TABLE Experiments (ExperimentID int IDENTITY(1,1) PRIMARY KEY, UserDefinedID varchar(50) NOT NULL,
    Note varchar(max) NULL, ScheduledToRun int NOT NULL DEFAULT 0);
CREATE TABLE ExperimentParameters (ExperimentID int NOT NULL, ParameterName varchar(50) NOT NULL, ParamValueTxt varchar(255) NULL);
CREATE TABLE ExperimentPlatePattern (ExperimentID int NOT NULL, WellID varchar(10) NOT NULL, WellAssign varchar(50) NOT NULL);
"""
PARAMETERS = dict(TargetWellVolume=700, MaxIteration=20, TopFractionToPropagate=1, InoculationOD=0.03,
                  GFP_scale=4669.1, GFP_RFPdamping=773.1, RFP_scale=2262.3, RFP_GFPdamping=305.0)
LAYOUT = [('A1', 'MediaCtrl'), ('A2', 'Cells'), ('B2', 'Cells')]


def manifest():
    return json.loads((ROOT / 'database_packages/champions-experiment/manifest.json').read_text(encoding='utf-8'))


def incubation_manifest():
    return dict(contract_version=3, id='incubation-check', name='Incubation check', version='1.0.0', libraries=[], tools=[
        dict(id='incubation-check', name='Incubation', kind='experiment', parameters=[
            dict(name='DurationHours', label='Duration', type='number', default=24, min=1, max=48, group='main'),
            dict(name='Condition', label='Condition', type='choice', default='Ambient', allowed=['Ambient', 'Warm'], group='main')])])


def archive(value):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zipped:
        zipped.writestr('manifest.json', json.dumps(value))
    return output.getvalue()


def package_checks(temporary):
    # Exercise the release's real ZIP builder and first-start catalogue path.
    sys.path.insert(0, str(ROOT / 'build_scripts'))
    from pyinstaller_build import _write_starter_packages
    defaults = ROOT / 'database_packages'
    release = temporary / 'starter-packages'
    _write_starter_packages(defaults, release)
    content = (release / 'champions-experiment.zip').read_bytes()
    installed, payloads = inspect_archive(content)
    assert set(payloads) == {'manifest.json'}
    assert installed.model_dump(exclude_none=True)['tools'][0]['kind'] == 'experiment'
    fresh = PackageCatalogue(temporary / 'fresh', defaults)
    assert fresh.resolve('champions-experiment', 'experiment')[2].name == 'Champions'
    empty = temporary / 'empty'
    empty.mkdir()
    existing = PackageCatalogue(temporary / 'existing', empty)
    existing = PackageCatalogue(existing.root, defaults)
    assert existing.tools('experiment') == [], 'Existing installation silently seeded Champions'
    existing.install(content)
    assert existing.export('champions-experiment')[0] == content
    assert existing.history('champions-experiment')[0]['version'] == '1.0.0'
    existing.remove('champions-experiment')
    assert PackageCatalogue(existing.root, defaults).tools('experiment') == []
    existing.install(content)
    assert len(existing.tools('experiment')) == 1
    print('ok   starter ZIP, fresh-only seeding, import/export/history/removal and explicit reimport')


def connect(database=DB):
    if database != DB:
        raise AssertionError('Only the named scratch database may be opened')
    return pyodbc.connect(f'DRIVER={DRIVER};SERVER={SERVER};DATABASE={DB};Trusted_Connection=yes;', autocommit=False, timeout=10)


def execute(sql, *args):
    with closing(connect()) as connection:
        cursor = connection.execute(sql, *args)
        rows = cursor.fetchall() if cursor.description else []
        connection.commit()
        return rows


def snapshot():
    with closing(connect()) as connection:
        return tuple(sorted(tuple(row) for row in connection.execute('SELECT * FROM ' + table))
                     for table in ('Experiments', 'ExperimentParameters', 'ExperimentPlatePattern'))


def assert_refused(response, text=None):
    body = response.json()
    assert response.status_code >= 400 or body.get('status') == 'error', body
    if text:
        assert text.lower() in json.dumps(body).lower(), body


def http_checks(client, service):
    types = client.get(BASE + '/types').json()
    assert [t['id'] for t in types] == ['champions-experiment', 'incubation-check'], types
    definition = types[0]
    assert {p['name']: p['default'] for p in definition['parameters']} == PARAMETERS
    assert [p['name'] for p in definition['parameters']] == list(PARAMETERS)
    def body(**changes):
        selected = next((t for t in types if t['id'] == changes.get('type_id')), definition)
        return dict(token=uuid.uuid4().hex, user_defined_id='check', note='note', schedule=0,
                    type_id=selected['id'], package_version=selected['package_version'], sha256=selected['sha256'],
                    parameters=dict(PARAMETERS), layout=list(LAYOUT)) | changes
    # Any connection attempt in these refusal cases is a failure, even if subsequently rolled back.
    with patch.object(service.sources, 'open', side_effect=AssertionError('Validation opened SQL')) as opened:
        assert client.post(BASE, json=body(type_id='missing')).status_code == 404
        assert client.post(BASE, json=body(package_version='9.0.0')).status_code == 409
        assert client.post(BASE, json=body(sha256='0' * 64)).status_code == 409
        for changes in [dict(user_defined_id=' '), dict(schedule=True), dict(schedule='1'), dict(schedule=2),
                        dict(token='invalid'), dict(note='x' * 4001), dict(unexpected=True),
                        dict(parameters={}), dict(parameters={**PARAMETERS, 'extra': 1}),
                        dict(parameters={**PARAMETERS, 'MaxIteration': 1.5}),
                        dict(parameters={**PARAMETERS, 'MaxIteration': True}),
                        dict(parameters={**PARAMETERS, 'MaxIteration': '20'}),
                        dict(parameters={**PARAMETERS, 'GFP_scale': 1}),
                        dict(parameters={**PARAMETERS, 'TopFractionToPropagate': 0.3}),
                        dict(layout=[('A1', 'MediaCtrl')]), dict(layout=[('A1', 'Cells'), ('A1', 'Cells')]),
                        dict(layout=[('I1', 'Cells')]), dict(layout=[('A1', 'other')])]:
            assert_refused(client.post(BASE, json=body(**changes)))
        cultures = [(f'{r}{c}', 'Cells') for c in range(1, 5) for r in 'ABCDEFGH']
        response = client.post(BASE, json=body(layout=cultures[:27], parameters={**PARAMETERS, 'TopFractionToPropagate': 0.5}))
        assert_refused(response, '27')
        assert '0.5' in response.text or '50%' in response.text, response.text
        for parameters in [dict(DurationHours=0, Condition='Ambient'), dict(DurationHours=49, Condition='Warm'),
                           dict(DurationHours=24, Condition='Cold')]:
            assert_refused(client.post(BASE, json=body(type_id='incubation-check', parameters=parameters, layout=[])))
        for headers, status in [({}, 401), ({'authorization': 'user'}, 403)]:
            saved = dict(client.headers)
            client.headers.clear()
            client.headers.update(headers)
            assert client.get(BASE + '/types').status_code == status
            assert client.post(BASE, json=body()).status_code == status
            client.headers.update(saved)
        assert client.get(BASE + '/types', headers={'x-forwarded-for': '203.0.113.1'}).status_code == 403
        assert client.post(BASE, json=body(), headers={'x-forwarded-for': '203.0.113.1'}).status_code == 403
        # Old journal records remain opaque: renaming the input must not change token replay.
        token = uuid.uuid4().hex
        historic = dict(status='unknown', message='Check whether experiment old exists before trying again.')
        with closing(sqlite3.connect(service.receipts)) as journal, journal:
            journal.execute('INSERT INTO receipts VALUES (?, ?, ?)', ('experiments:' + token, 'admin', json.dumps(historic)))
        assert client.post(BASE, json=body(token=token)).json() == historic
        assert client.post(BASE, json=body(token=token), headers={'authorization': 'another-admin'}).status_code == 404
        service.catalogue.remove('champions-experiment')
        assert client.post(BASE, json=body(token=token)).json() == historic
        assert client.post(BASE, json=body()).status_code == 404
        service.catalogue.install(archive(manifest()))
        # Simulate the actual update between a successful page load and submission.
        definition.update(client.get(BASE + '/types').json()[0])
        changed = manifest()
        changed['tools'][0]['name'] = 'Champions updated'
        service.catalogue.install(archive(changed))
        assert client.post(BASE, json=body()).status_code == 409
        definition.update(client.get(BASE + '/types').json()[0])
        changed['version'] = '1.0.1'
        service.catalogue.install(archive(changed))
        assert client.post(BASE, json=body()).status_code == 409
        service.catalogue.install(archive(manifest()))
        definition.update(client.get(BASE + '/types').json()[0])
        assert opened.call_count == 0
    print('ok   HTTP identity, validation, access, removed definition and historical unknown receipt replay')
    return body


def handoff_checks(client, service):
    # Read-only HTTP boundary: resolution, binding identity and active-state replies.
    token = uuid.uuid4().hex
    path = BASE + '/123/schedule-draft?token=' + token
    receipt = dict(status='succeeded', result=dict(experiment_id=123), server=SERVER, database=DB)
    with closing(sqlite3.connect(service.receipts)) as journal, journal:
        journal.execute('INSERT INTO receipts VALUES (?, ?, ?)',
                        ('experiments:' + token, 'admin', json.dumps(receipt)))
    assert client.get(path).status_code == 404
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as zipped:
        for file in (ROOT / 'database_packages/evoyeast-experiment').glob('*'):
            if file.is_file():
                zipped.write(file, file.name)
    service.catalogue.install(output.getvalue())
    assert client.get(path).status_code == 409
    original = service.sources.state
    target = dict(server=SERVER, database=DB, access='operation')
    service.sources.state = dict(original, sources={'writer': target, 'reader': dict(target, access='read')},
        bindings={'evoyeast-experiment': {'primary': 'reader'}},
        operation_bindings={'experiments': 'writer', 'evoyeast-experiment': 'writer'})
    try:
        with patch.object(service.sources, 'open', side_effect=AssertionError('Handoff opened SQL')):
            assert client.get(path).json() == dict(tool_id='evoyeast-experiment', inputs=dict(experiment_id=123),
                expected_origin=dict(server=SERVER, database=DB))
            assert client.get(BASE + '/0/schedule-draft').status_code == 400
            for source_id in ['reader', 'other-writer']:
                service.sources.state['sources'][source_id] = dict(target, database='Different',
                    access='read' if source_id == 'reader' else 'operation')
                if source_id == 'other-writer':
                    service.sources.state['operation_bindings']['evoyeast-experiment'] = source_id
                assert_refused(client.get(path), 'registration database')
                service.sources.state['sources'][source_id]['database'] = DB
        assert client.get(path, headers={'authorization': 'another-admin'}).status_code == 404
        with closing(sqlite3.connect(service.receipts)) as journal, journal:
            journal.execute('UPDATE receipts SET result=? WHERE id=?',
                            (json.dumps(dict(status='succeeded', result=dict(experiment_id=123))), 'experiments:' + token))
        assert_refused(client.get(path), 'origin')
        class ActiveConnection:
            rows = []
            def execute(self, sql):
                assert sql == ('SELECT ExperimentID, UserDefinedID FROM dbo.Experiments '
                               'WHERE ScheduledToRun = 1 ORDER BY ExperimentID')
                return self
            def fetchall(self):
                return self.rows
        connection = ActiveConnection()
        @contextmanager
        def read_active(source):
            assert source == target
            yield connection
        with patch.object(service.sources, 'open', read_active):
            for rows in [[], [(12, 'one')], [(12, 'one'), (13, 'two')]]:
                connection.rows = rows
                assert client.get(BASE + '/active').json() == [dict(experiment_id=id, user_defined_id=name) for id, name in rows]
        with patch.object(service.sources, 'open', side_effect=PackageError('Lookup failed', 409)):
            assert_refused(client.get(BASE + '/active'), 'Lookup failed')
        for route in [path, BASE + '/active']:
            assert client.get(route, headers={'authorization': 'user'}).status_code == 403
            assert client.get(route, headers={'x-forwarded-for': '203.0.113.1'}).status_code == 403
    finally:
        service.sources.state = original
    print('ok   scheduling draft binding resolution, no writes, active empty/single/multiple/error and access')


def sql_checks(client, service, body, lhr, lab, scratch):
    sys.path[:0] = [str(lhr / 'src'), str(lhr / 'VENUS Python Modules' / 'Champions_FL' / 'BeginNewExperiment')]
    import RegisterNewExperiment as exe
    import pandas as pd
    procedure = (lab / 'tasks/evoyeast_procedures_2026-11-17/ScheduleExperimentForImmediateExecution.sql').read_text(encoding='utf-8-sig')
    master = pyodbc.connect(f'DRIVER={DRIVER};SERVER={SERVER};DATABASE=master;Trusted_Connection=yes;', autocommit=True, timeout=10)
    created = False
    try:
        if master.execute('SELECT 1 FROM sys.databases WHERE name = ?', DB).fetchone():
            raise RuntimeError(f'{DB} already exists; refusing to use or drop it.')
        master.execute(f'CREATE DATABASE {DB} COLLATE SQL_Latin1_General_CP1_CS_AS')
        created = True
        with closing(connect()) as connection:
            for statement in TABLES.split(';'):
                if statement.strip():
                    connection.execute(statement)
            connection.execute(procedure)
            connection.commit()
        # These are the only source fields used by this check's scratch-only opener.
        target = dict(id='scratch', name='Scratch', server=SERVER, database=DB, access='operation')
        service.sources.state['sources'] = {'scratch': target}
        service.sources.state['operation_bindings'] = {'experiments': 'scratch'}
        @contextmanager
        def open_scratch(source):
            assert source == target or source == dict(target, access='read'), 'Unexpected connection target'
            with closing(connect()) as connection:
                yield connection
        service.sources.open = open_scratch
        assert client.get(BASE + '/active').json() == []
        execute("INSERT INTO Experiments (UserDefinedID, ScheduledToRun) VALUES ('active-check', 1)")
        active = client.get(BASE + '/active').json()
        assert len(active) == 1 and active[0]['user_defined_id'] == 'active-check'
        execute("DELETE FROM Experiments WHERE UserDefinedID = 'active-check'")
        # Reuse the scratch opener for a different configured target holding the same ID.
        request = body(user_defined_id='origin-check')
        response = client.post(BASE, json=request)
        assert response.status_code == 200 and response.json()['status'] == 'succeeded', response.text
        experiment_id = response.json()['result']['experiment_id']
        path = BASE + f'/{experiment_id}/schedule-draft?token=' + request['token']
        reader = dict(target, access='read')
        service.sources.state['sources']['reader'] = reader
        service.sources.state['bindings'] = {'evoyeast-experiment': {'primary': 'reader'}}
        service.sources.state['operation_bindings']['evoyeast-experiment'] = 'scratch'
        draft = client.get(path)
        assert draft.status_code == 200, draft.text
        step = draft.json()
        from backend.api.scheduling import _requested_preparation
        def pin():
            with patch('backend.services.database_tools.get_database_tools', return_value=service):
                return _requested_preparation({'preparation': step}, {'username': 'admin', 'role': 'admin'})
        assert pin()['inputs']['experiment_id'] == experiment_id
        for changes in [dict(database='Different'), dict(server='Different')]:
            before = dict(target)
            target.update(changes)
            reader.update(changes)
            assert_refused(client.get(path), 'registration database')
            try:
                pin()
                raise AssertionError('Changed registration target was accepted')
            except HTTPException as exc:
                assert exc.status_code == 409 and 'registration database' in exc.detail
            target.update(before)
            reader.update(before, access='read')
        target.update(server=' ' + SERVER.lower() + ' ', database=' ' + DB.lower() + ' ')
        reader.update(server=target['server'], database=target['database'])
        assert client.get(path).status_code == 200
        assert pin()['inputs']['experiment_id'] == experiment_id
        target.update(server=SERVER, database=DB)
        reader.update(server=SERVER, database=DB)
        definition = client.get(BASE + '/types').json()[0]
        def submit(**changes):
            request = body(**changes)
            selected = next(t for t in client.get(BASE + '/types').json() if t['id'] == request['type_id'])
            request.update(package_version=selected['package_version'], sha256=selected['sha256'])
            return client.post(BASE, json=request)
        def success(**changes):
            response = submit(**changes)
            result = response.json()
            assert response.status_code == 200 and result['status'] == 'succeeded', result
            return result['result']
        def refused(**changes):
            before = snapshot()
            response = submit(**changes)
            assert_refused(response)
            assert snapshot() == before, response.text
            return response
        def stored(experiment_id):
            with closing(connect()) as connection:
                values = sorted((n, float(v)) for n, v in connection.execute(
                    'SELECT ParameterName, ParamValueTxt FROM ExperimentParameters WHERE ExperimentID=?', experiment_id))
                wells = sorted(tuple(r) for r in connection.execute(
                    'SELECT WellID, WellAssign FROM ExperimentPlatePattern WHERE ExperimentID=?', experiment_id))
                parent = tuple(connection.execute('SELECT Note,ScheduledToRun FROM Experiments WHERE ExperimentID=?', experiment_id).fetchone())
                return parent, values, wells
        reference_parameters = {p['name']: p['default'] for p in definition['parameters']}
        reference_layout = definition['layout']['default']
        assert reference_parameters == PARAMETERS and len(reference_layout) == 40
        excel = io.BytesIO()
        pd.DataFrame([dict(Destination=well, Source='T' if assignment == 'MediaCtrl' else 'culture', Vol=1)
                      for well, assignment in reference_layout]).to_excel(excel, index=False, startrow=1)
        for schedule in (0, 1):
            mine = success(user_defined_id=f'rc_{schedule}', schedule=schedule,
                           parameters=reference_parameters, layout=reference_layout)['experiment_id']
            excel.seek(0)
            with closing(connect()) as connection:
                theirs = exe.insert_experiment(connection.cursor(), f'exe_{schedule}', 'note', str(schedule), reference_parameters, excel)
                connection.commit()
            a, b = stored(mine), stored(theirs)
            assert a[1:] == b[1:] and a[0][0] == b[0][0] and len(a[1]) == 8, (a, b)
            assert execute('SELECT UserDefinedID FROM Experiments WHERE ExperimentID=?', mine)[0][0] == f'rc_{schedule}'
        assert [r[0] for r in execute('SELECT UserDefinedID FROM Experiments WHERE ScheduledToRun=1')] == ['exe_1']
        print('ok   eight-field rows and wells equal the exe; scheduling activates only the intended experiment')
        cultures = [(f'{r}{c}', 'Cells') for c in range(1, 5) for r in 'ABCDEFGH']
        refused(layout=cultures[:27], parameters={**PARAMETERS, 'TopFractionToPropagate': 0.5})
        success(user_defined_id='whole32', layout=cultures, parameters={**PARAMETERS, 'TopFractionToPropagate': 0.5})
        refused(user_defined_id='x' * 51)
        for populated in ('parameters', 'plate layout', 'parameters and plate layout'):
            parent = execute('INSERT INTO Experiments (UserDefinedID,Note) OUTPUT INSERTED.ExperimentID VALUES (?,?)', populated, 'kept')[0][0]
            if 'parameters' in populated:
                execute('INSERT INTO ExperimentParameters VALUES (?,?,?)', parent, 'Existing', '42')
            if 'plate layout' in populated:
                execute('INSERT INTO ExperimentPlatePattern VALUES (?,?,?)', parent, 'H12', 'Cells')
            assert populated in refused(user_defined_id=populated).text
        parent = execute("INSERT INTO Experiments (UserDefinedID,Note,ScheduledToRun) OUTPUT INSERTED.ExperimentID VALUES ('empty','preserved',1)")[0][0]
        result = success(user_defined_id='empty', note='ignored')
        assert result['experiment_id'] == parent and result['reused_existing'] is True, result
        assert stored(parent)[0] == ('preserved', 1)
        refused(user_defined_id='empty')
        execute("INSERT INTO Experiments (UserDefinedID) VALUES ('ambiguous'),('ambiguous')")
        assert 'more than one' in refused(user_defined_id='ambiguous').text
        print('ok   whole counts, SQL column failure, empty reuse and populated/ambiguous refusal')
        # Genuine independent transactions race for the same UserDefinedID.
        barrier = threading.Barrier(2)
        concurrent_service = DatabaseTools(service.root, scratch, guard=nullcontext)
        concurrent_service.sources.state['sources'] = {'scratch': target}
        concurrent_service.sources.state['operation_bindings'] = {'experiments': 'scratch'}
        concurrent_service.sources.open = open_scratch
        def register_concurrently(active_service):
            barrier.wait(timeout=10)
            request = body(user_defined_id='concurrent', package_version=definition['package_version'], sha256=definition['sha256'])
            return active_service.register_experiment(request.pop('token'), request, 'admin', None)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(register_concurrently, (service, concurrent_service)))
        finally:
            concurrent_service.close()
        assert sorted(r['status'] for r in results) == ['error', 'succeeded'], results
        assert execute("SELECT COUNT(*) FROM Experiments WHERE UserDefinedID='concurrent'")[0][0] == 1
        # Mutation is blocked for the entire SQL operation, not just while resolving.
        @contextmanager
        def reserved_open(source):
            for mutate in (lambda: service.catalogue.remove('champions-experiment'), lambda: service.catalogue.install(archive(manifest()))):
                try:
                    mutate()
                except PackageError as exc:
                    assert exc.status == 409
                else:
                    raise AssertionError('Running definition mutated')
            with open_scratch(source) as connection:
                yield connection
        with patch.object(service.sources, 'open', reserved_open):
            success(user_defined_id='reserved')
        execute("CREATE TRIGGER block_schedule ON Experiments AFTER UPDATE AS BEGIN RAISERROR('blocked',16,1); END")
        refused(user_defined_id='schedule_failure', schedule=1)
        execute("INSERT INTO Experiments (UserDefinedID) VALUES ('reuse_failure')")
        refused(user_defined_id='reuse_failure', schedule=1)
        execute('DROP TRIGGER block_schedule')
        execute('ALTER PROCEDURE dbo.ScheduleExperimentForImmediateExecution @UserDefinedExptID varchar(255) AS BEGIN ROLLBACK TRANSACTION; END')
        refused(user_defined_id='lost_transaction', schedule=1)
        execute(procedure.replace('CREATE PROCEDURE', 'ALTER PROCEDURE'))
        print('ok   concurrent IDs, definition reservation and scheduling rollback for new/reused rows')
        # A lost commit acknowledgment must persist unknown and never run SQL again.
        class LostCommit:
            def __init__(self, connection):
                object.__setattr__(self, 'connection', connection)
            def __getattr__(self, name):
                return getattr(self.connection, name)
            def __setattr__(self, name, value):
                setattr(self.connection, name, value)
            def commit(self):
                self.connection.commit()
                raise OSError('commit acknowledgement lost')
        @contextmanager
        def lost_commit(source):
            with open_scratch(source) as connection:
                yield LostCommit(connection)
        request = body(user_defined_id='unknown', package_version=definition['package_version'], sha256=definition['sha256'])
        with patch.object(service.sources, 'open', lost_commit):
            result = client.post(BASE, json=request).json()
        assert result['status'] == 'unknown' and "UserDefinedID 'unknown'" in result['message'], result
        before = snapshot()
        with patch.object(service.sources, 'open', side_effect=AssertionError('Replay opened SQL')):
            assert client.post(BASE, json=request).json() == result
        assert snapshot() == before
        # A second process instance reads the same durable receipt after package removal.
        service.catalogue.remove('champions-experiment')
        restarted = DatabaseTools(service.root, scratch, guard=nullcontext)
        try:
            with patch.object(restarted.sources, 'open', side_effect=AssertionError('Restart replay opened SQL')):
                inputs = dict(request)
                token = inputs.pop('token')
                assert restarted.register_experiment(token, inputs, 'admin', None) == result
        finally:
            restarted.close()
        service.catalogue.install(archive(manifest()))
        definition = client.get(BASE + '/types').json()[0]
        # A no-layout type may complete an empty parent even when it has pattern rows.
        parent = execute("INSERT INTO Experiments (UserDefinedID) OUTPUT INSERTED.ExperimentID VALUES ('pattern_only')")[0][0]
        execute('INSERT INTO ExperimentPlatePattern VALUES (?,?,?)', parent, 'A1', 'Cells')
        result = success(user_defined_id='pattern_only', type_id='incubation-check', layout=[],
                         parameters=dict(DurationHours=24, Condition='Ambient'))
        assert result['experiment_id'] == parent and result['reused_existing']
        assert execute('SELECT WellID FROM ExperimentPlatePattern WHERE ExperimentID=?', parent)[0][0] == 'A1'
        # No-layout types neither query nor write the pattern table.
        execute('DROP TABLE ExperimentPlatePattern')
        for number in (1, 48):
            success(user_defined_id=f'incubation_{number}', type_id='incubation-check', layout=[],
                    parameters=dict(DurationHours=number, Condition='Warm'))
        print('ok   uncertain commit survives restart/removal; no-layout works without a pattern table')
    finally:
        if created:
            master.execute(f'ALTER DATABASE {DB} SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            master.execute(f'DROP DATABASE {DB}')
        master.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('lhr', nargs='?', type=Path, default=ROOT.parent / 'Shou_LHR_PythonPackage')
    parser.add_argument('lab', nargs='?', type=Path, default=ROOT.parent / 'Shou_Lab')
    parser.add_argument('--contract-only', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='rc-experiment-') as temporary:
        package_checks(Path(temporary))
        scratch = Path(temporary) / 'defaults'
        scratch.mkdir()
        service = DatabaseTools(Path(temporary) / 'tools', scratch, guard=nullcontext)
        service.catalogue.in_use = lambda _: []
        app = FastAPI()
        app.include_router(router)
        def user(request: Request):
            name = request.headers.get('authorization')
            if not name:
                raise HTTPException(401)
            return dict(username=name, role='user' if name == 'user' else 'admin')
        app.dependency_overrides[get_current_user] = user
        app.dependency_overrides[get_database_tools] = lambda: service
        try:
            service.catalogue.install(archive(manifest()))
            service.catalogue.install(archive(incubation_manifest()))
            with patch('backend.services.database_tools.log_action'), TestClient(app, client=('127.0.0.1', 1234), headers={'authorization': 'admin'}) as client:
                body = http_checks(client, service)
                handoff_checks(client, service)
                if not args.contract_only:
                    sql_checks(client, service, body, args.lhr, args.lab, scratch)
        finally:
            service.close()
    print('all requested checks passed' if not args.contract_only else 'HTTP/catalogue checks passed; SQL not requested')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
