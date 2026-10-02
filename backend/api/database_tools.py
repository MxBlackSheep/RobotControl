"""Authenticated public interface; never accepts SQL or Python entry points."""
from typing import Any, Literal
from contextlib import nullcontext
import sqlite3
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from backend.api.dependencies import require_local_access, ConnectionContext, get_connection_context
from backend.services.auth import get_current_user
from backend.services.database_tools import get_database_tools
from backend.services.database_packages import MAX_UPLOAD, PackageError
from backend.utils.audit import log_action
from backend.services.report_authoring import ReportDraft, inspect_python
from backend.services.report_sources import ReportSource, lookup_rows
from backend.services.database_access import ProvisionAuthority
from backend.services.sqlite_safety import SafetyConflict, StorageUnavailable


class ToolRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            if request.method in {'POST', 'PUT'} and '/packages' not in request.url.path:
                try:
                    length = int(request.headers.get('content-length', '-1'))
                except ValueError:
                    raise HTTPException(400, 'Invalid request length')
                if length < 0 or length > 4 * 1024 * 1024:
                    raise HTTPException(413, 'Request requires Content-Length and must be under 4 MiB')
            if request.method == 'POST' and request.url.path.rstrip('/').endswith(('/packages', '/packages/inspect')):
                try:
                    length = int(request.headers.get('content-length', '-1'))
                except ValueError:
                    raise HTTPException(400, 'Invalid upload length')
                if length < 0:
                    raise HTTPException(411, 'Package uploads require Content-Length')
                if length > MAX_UPLOAD + 1024 * 1024:
                    raise HTTPException(413, 'Package exceeds the 20 MiB upload limit')
            try:
                return await original(request)
            except PackageError as exc:
                raise HTTPException(exc.status, str(exc)) from exc
            except SafetyConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except StorageUnavailable:
                raise HTTPException(503, 'Scheduler safety storage is unavailable.') from None
            except sqlite3.Error:
                raise HTTPException(503, 'Local database storage is unavailable. Check the application logs before retrying.') from None
            except ValidationError as exc:
                error = exc.errors()[0]
                raise HTTPException(400, f"{'.'.join(map(str, error['loc'])) or 'Report'}: {error['msg']}") from exc
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        return handler


router = APIRouter(prefix='/api/database/tools', tags=['database'], route_class=ToolRoute,
                   dependencies=[Depends(get_current_user)])


# Tool kinds that write through the package's operation connection.
WRITING_KINDS = {'operation', 'preparation'}


def local_admin(user=Depends(get_current_user), connection: ConnectionContext=Depends(require_local_access)):
    if user.get('role') != 'admin':
        raise HTTPException(403, 'Local administrator required')
    return user


def owner(user):
    return str(user.get('user_id') or user['username'])


class Inputs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    inputs: dict[str, Any] = Field(default_factory=dict, max_length=20)


class Execution(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(pattern=r'^[0-9a-f]{32}$')
    confirmation: str = Field(max_length=2000)


@router.get('/catalogue')
def catalogue(kind: Literal['operation', 'report', 'preparation'], user=Depends(get_current_user), service=Depends(get_database_tools)):
    if kind in ('operation', 'preparation') and user.get('role') != 'admin':
        return []
    return service.public_catalogue(kind)


class ChoiceRequest(Inputs):
    search: str = Field(default='', max_length=200)
    page: int = Field(default=1, ge=1, le=100000)


@router.post('/reports/{tool_id}/choices/{field_name}')
def report_choices(tool_id: str, field_name: str, payload: ChoiceRequest, service=Depends(get_database_tools)):
    return service.choices(tool_id, field_name, payload.inputs, payload.search, payload.page)


@router.post('/operations/{tool_id}/choices/{field_name}')
def operation_choices(tool_id: str, field_name: str, payload: ChoiceRequest, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.choices(tool_id, field_name, payload.inputs, payload.search, payload.page, kind='operation')


@router.post('/preparations/{tool_id}/choices/{field_name}')
def preparation_choices(tool_id: str, field_name: str, payload: ChoiceRequest, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.choices(tool_id, field_name, payload.inputs, payload.search, payload.page, kind='preparation')


@router.get('/sources')
def sources(user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.sources.list()


@router.get('/viewer-sources')
def viewer_sources(service=Depends(get_database_tools)):
    source = service.sources.viewer()
    return [{k: source.get(k) for k in ('id', 'name', 'server', 'database', 'revision')}] if source else []


class ViewerSelection(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)


@router.put('/viewer-source')
def select_viewer(payload: ViewerSelection, user=Depends(local_admin), service=Depends(get_database_tools)):
    service.sources.set_viewer(payload.source_id)
    log_action(actor=owner(user), action='select_viewer_database', scope='database', client_ip=None, success=True, details={'source_id':payload.source_id})
    return viewer_sources(service)


@router.post('/sources')
def save_source(payload: ReportSource, user=Depends(local_admin), service=Depends(get_database_tools)):
    result = service.sources.save(payload)
    log_action(actor=owner(user), action='save_report_source', scope='database', client_ip=None, success=True, details={'id': payload.id})
    return result


@router.post('/sources/access/review')
def review_access(payload: ReportSource, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.access.review(payload, owner(user))


@router.post('/sources/access/create')
def create_access(payload: ProvisionAuthority, user=Depends(local_admin), service=Depends(get_database_tools)):
    try:
        result = service.access.create(payload, owner(user))
    except PackageError:
        log_action(actor=owner(user), action='create_database_reader', scope='database', client_ip=None, success=False, details={'review': payload.token})
        raise
    log_action(actor=owner(user), action='create_database_reader', scope='database', client_ip=None, success=True, details={'review': payload.token})
    return result


@router.delete('/sources/{source_id}')
def delete_source(source_id: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    service.sources.remove(source_id)
    return {'message': 'Connection removed.'}


class Mappings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mappings: dict[str, str] = Field(max_length=8)
    operation_source: str | None = Field(default=None, max_length=64)


@router.get('/packages/{package_id}/sources')
def package_sources(package_id: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    with service.catalogue.lock:
        entry = service.catalogue.index.get(package_id)
        if not entry:
            raise HTTPException(404, 'Package not found')
        return dict(aliases=service.sources.aliases(entry['manifest']), mappings=service.sources.bindings(package_id),
                    has_operation=any(t['kind'] in WRITING_KINDS for t in entry['manifest']['tools']),
                    operation_source=service.sources.state['operation_bindings'].get(package_id))


@router.put('/packages/{package_id}/sources')
def bind_sources(package_id: str, payload: Mappings, user=Depends(local_admin), service=Depends(get_database_tools)):
    with service.catalogue.lock:
        entry = service.catalogue.index.get(package_id)
        if not entry:
            raise HTTPException(404, 'Package not found')
        if service.catalogue.running.get(package_id):
            raise HTTPException(409, 'Package is running. Wait until it finishes.')
        with service.sources.lock:
            if payload.operation_source:
                if not any(t['kind'] in WRITING_KINDS for t in entry['manifest']['tools']):
                    raise HTTPException(400, 'Package has no operation or preparation step')
                service.sources.get(payload.operation_source, 'operation')
            if payload.operation_source != service.sources.state['operation_bindings'].get(package_id):
                # A pinned preparation step must keep writing to the connection it was saved with.
                service.catalogue.refuse_if_scheduled(package_id)
            service.sources.bind(package_id, service.sources.aliases(entry['manifest']), payload.mappings)
            service.sources.bind_operation(package_id, payload.operation_source)
    return {'message': 'Connections assigned.'}


class DraftSave(BaseModel):
    model_config = ConfigDict(extra='forbid')
    draft: ReportDraft
    revision: int = Field(default=0, ge=0)


class PythonUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source: str = Field(max_length=1024*1024)


class ToolUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    files: dict[str, str] = Field(max_length=99)
    key: str | None = None
    revision: int = Field(default=0, ge=0)
    mode: Literal['all', 'python', 'supporting'] = 'all'


@router.post('/authoring/import')
def import_tool(payload: ToolUpload, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.authoring.import_files(payload.files, owner(user), payload.key, payload.revision, payload.mode)


@router.get('/authoring/examples/{kind}')
def authoring_example(kind: Literal['report', 'operation'], user=Depends(local_admin)):
    import sys
    from pathlib import Path
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
    return Response((root / 'database_packages' / 'examples' / f'{kind}.py').read_text('utf-8'),
                    media_type='text/x-python', headers={'Content-Disposition': f'attachment; filename="{kind}.py"'})


@router.get('/drafts/{key}/source')
def tool_source(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    from backend.services.tool_definition import source_archive
    draft = service.authoring.draft(key, owner(user))
    if not draft.definition_file:
        raise PackageError('Use the editing files for this older draft.')
    if len(draft.files) == 1:
        return Response(draft.files[draft.definition_file], media_type='text/x-python',
                        headers={'Content-Disposition': f'attachment; filename="{draft.definition_file}"'})
    return Response(source_archive(draft.files), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="{draft.package_id}-source.zip"'})


@router.post('/authoring/{kind}/{tool_id}/edit')
def edit_defined_tool(kind: Literal['report', 'operation'], tool_id: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.authoring.edit_installed(tool_id, owner(user), kind, code_defined=True)


@router.post('/authoring/inspect-python')
def inspect_script(payload: PythonUpload, user=Depends(local_admin)):
    return inspect_python(payload.source)


@router.get('/drafts')
def drafts(user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.authoring.list(owner(user))


@router.post('/reports/{tool_id}/edit')
def edit_report(tool_id: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.authoring.edit_installed(tool_id, owner(user))


@router.post('/drafts')
def new_draft(payload: DraftSave, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.authoring.save(payload.draft, owner(user))


@router.get('/drafts/{key}')
def get_draft(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.authoring.get(key, owner(user))


@router.put('/drafts/{key}')
def save_draft(key: str, payload: DraftSave, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.authoring.save(payload.draft, owner(user), key, payload.revision)


@router.delete('/drafts/{key}')
def delete_draft(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    service.authoring.remove(key, owner(user))
    return {'message': 'Draft removed.'}


@router.get('/drafts/{key}/handler')
def starter(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    return Response(service.authoring.starter(key, owner(user)), media_type='text/x-python',
                    headers={'Content-Disposition': 'attachment; filename="handler.py"'})


@router.get('/drafts/{key}/package')
def export_draft(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    draft = service.authoring.draft(key, owner(user))
    return Response(service.authoring.archive(draft, key, owner(user)), media_type='application/zip',
                    headers={'Content-Disposition': f'attachment; filename="{draft.package_id}-{draft.version}.zip"'})


@router.get('/drafts/{key}/review')
def review_draft(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    with service.authoring.lock, service.catalogue.lock, service.sources.lock:
        service.authoring.check_base(key, owner(user))
        return service.catalogue.inspect(service.authoring.archive(service.authoring.draft(key, owner(user)), key, owner(user)))


@router.post('/drafts/{key}/choices/{field_name}')
def draft_choices(key: str, field_name: str, payload: ChoiceRequest, user=Depends(local_admin), service=Depends(get_database_tools)):
    draft = service.authoring.draft(key, owner(user))
    tool = draft.manifest().tools[0]
    values = tool.validate_values(payload.inputs, partial=True)
    field = next((x for x in tool.inputs if x.name == field_name and x.lookup), None)
    if not field:
        raise HTTPException(404, 'Choice not found')
    snapshot = service.sources.snapshot(draft.package_id, tool.sources, draft.mappings)
    with service.sources.open(snapshot[field.lookup.source]) as conn:
        return lookup_rows(conn, field, values, payload.search, payload.page)


class DraftTrial(Inputs):
    revision: int | None = None


@router.post('/drafts/{key}/try')
def try_draft(key: str, payload: DraftTrial, user=Depends(local_admin), service=Depends(get_database_tools)):
    # Explicit trial permits importing the trusted handler; loading forms does not.
    operation = service.authoring.draft(key, owner(user)).kind == 'operation'
    with service.guard() if operation else nullcontext():
        with service.authoring.lock, service.lock, service.catalogue.lock, service.sources.lock:
            saved = service.authoring.get(key, owner(user))
            if saved['draft'].get('definition_file') and payload.revision != saved['revision']:
                raise PackageError('Draft changed. Reload it before trying.', 409)
            service.authoring.clear_trial(key, owner(user))
            draft = service.authoring.trial(key, owner(user))
            if (draft.kind == 'operation') != operation:
                raise PackageError('Tool type changed. Try again.', 409)
            if operation:
                result = service.preview_draft(draft, payload.inputs)
            else:
                result = service.start_report(draft.package_id, payload.inputs, owner(user), service.authoring.trials, draft.mappings)
            service.authoring.record_trial(key, owner(user), saved['revision'], None if operation else result['id'])
            return result


@router.post('/drafts/{key}/check')
def check_tool_setup(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    with service.authoring.lock, service.catalogue.lock, service.sources.lock:
        service.authoring.check_base(key, owner(user))
        draft = service.authoring.draft(key, owner(user))
        service.catalogue.inspect(service.authoring.archive(draft, key, owner(user)))
        snapshot = service.sources.snapshot(draft.package_id, draft.sources, draft.mappings)
        with service.sources.connections(snapshot):
            pass
        if draft.kind == 'operation':
            with service.sources.open(service.sources.get(draft.operation_source, 'operation')):
                pass
        return dict(message='Files, libraries and connections checked. Python has not been run.')


class DraftInstall(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_current: str = Field(max_length=64)
    revision: int = Field(ge=1)
    reviewed: bool = False
    change_note: str | None = Field(default=None, max_length=2000)


@router.post('/drafts/{key}/install')
def install_draft(key: str, payload: DraftInstall, user=Depends(local_admin), service=Depends(get_database_tools)):
    with service.authoring.lock, service.lock, service.catalogue.lock, service.sources.lock:
        published = service.catalogue.published_draft(key, owner(user))
        if published:
            entry, receipt = published
            if receipt['draft']['revision'] != payload.revision or entry['sha256'] != receipt['sha256']:
                raise PackageError('This draft was already published; the installed version has since changed.', 409)
            return entry['manifest']
        if service.authoring.get(key, owner(user))['revision'] != payload.revision:
            raise HTTPException(409, 'Draft changed. Review it again.')
        draft = service.authoring.draft(key, owner(user))
        if draft.definition_file:
            if not payload.reviewed:
                raise PackageError('Review the trial result before enabling this tool.', 409)
            service.authoring.require_trial(key, owner(user))
        baseline = service.authoring.check_base(key, owner(user))
        note = payload.change_note if payload.change_note is not None else draft.change_note
        content = service.authoring.archive(draft, key, owner(user), note=note)
        from backend.services.database_packages import inspect_archive
        manifest, _ = inspect_archive(content)
        aliases = service.sources.aliases(manifest.model_dump())
        mappings = {**(baseline['mappings'] if baseline else {}), **draft.mappings}
        mappings = {name:mappings[name] for name in aliases if name in mappings}
        service.sources.snapshot(draft.package_id, aliases, mappings)
        if set(mappings) != set(aliases):
            raise HTTPException(400, 'Map exactly the declared source aliases.')
        operation_source = draft.operation_source
        if any(t.kind == 'operation' for t in manifest.tools):
            operation_source = operation_source or service.sources.state['operation_bindings'].get(draft.package_id)
            if draft.definition_file:
                service.sources.get(operation_source, 'operation')
        # Save connection assignments first under both locks; restore on failure.
        # The package index remains the single activation point. No reader can
        # observe a half-enabled tool in this process.
        import copy
        old_sources = copy.deepcopy(service.sources.state)
        service.authoring.begin_activation(draft.package_id, content)
        try:
            service.sources.bind(draft.package_id, aliases, mappings)
            if operation_source:
                service.sources.bind_operation(draft.package_id, operation_source)
            result = service.catalogue.install(content, expected_current=payload.expected_current, actor=owner(user),
                note=note,
                draft=dict(id=key, revision=payload.revision))
        except Exception:
            service.sources._save(old_sources)
            service.authoring.finish_activation()
            raise
        service.authoring.finish_activation()
        try:
            service.authoring.remove(key, owner(user))
        except Exception:
            # The history receipt already hides this completed draft and prevents
            # publishing twice, even if cleanup cannot finish or the response is lost.
            import logging
            logging.getLogger(__name__).exception('Published draft cleanup failed: %s', key)
    log_action(actor=owner(user), action='install_report_draft', scope='database', client_ip=None, success=True,
               details={'package': result['id'], 'version': result['version']})
    return result


@router.get('/experiments')
def experiments(search: str = Query('', max_length=200), page: int = Query(1, ge=1), report_id: str | None = None,
                operation_id: str | None = None, user=Depends(get_current_user),
                connection: ConnectionContext=Depends(get_connection_context),
                service=Depends(get_database_tools)):
    if report_id:
        return service.report_experiments(report_id, search, page)
    if not operation_id:
        raise HTTPException(400, 'Choose an operation or report first')
    if user.get('role') != 'admin' or not connection.is_local:
        raise HTTPException(403, 'Local administrator required')
    return service.operation_experiments(operation_id, search, page)


@router.get('/packages')
def packages(user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.catalogue.packages()


@router.get('/packages/{package_id}/export')
def export_package(package_id: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    content, filename = service.catalogue.export(package_id)
    return Response(content, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@router.get('/packages/{package_id}/history')
def package_history(package_id: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.catalogue.history(package_id)


@router.get('/drafts/{key}/editing-files')
def editing_files(key: str, user=Depends(local_admin), service=Depends(get_database_tools)):
    return Response(service.authoring.editing_files(key, owner(user)), media_type='application/zip',
                    headers={'Content-Disposition': 'attachment; filename="report-editing-files.zip"'})


@router.post('/packages')
def install(file: UploadFile = File(...), user=Depends(local_admin),
            expected_current: str | None = Form(None), expected_package: str | None = Form(None),
            change_note: str = Form('', max_length=2000),
            connection: ConnectionContext=Depends(require_local_access), service=Depends(get_database_tools)):
    try:
        result = service.catalogue.install(file.file.read(MAX_UPLOAD+1),
            expected_current='' if expected_current == 'absent' else expected_current,
            expected_package=expected_package, actor=owner(user), note=change_note)
        log_action(actor=owner(user), action='install_database_package', scope='database', client_ip=connection.client_ip,
                   success=True, details=dict(package=result['id'], version=result['version']))
        return result
    finally:
        file.file.close()


@router.post('/packages/inspect')
def inspect_package(file: UploadFile = File(...), user=Depends(local_admin), service=Depends(get_database_tools)):
    try:
        return service.catalogue.inspect(file.file.read(MAX_UPLOAD+1))
    finally:
        file.file.close()


@router.delete('/packages/{package_id}')
def remove(package_id: str, user=Depends(local_admin),
           connection: ConnectionContext=Depends(require_local_access), service=Depends(get_database_tools)):
    service.catalogue.remove(package_id)
    service.sources.unbind(package_id)
    log_action(actor=owner(user), action='remove_database_package', scope='database', client_ip=connection.client_ip,
               success=True, details=dict(package=package_id))
    return dict(message='Package removed.')


@router.post('/operations/{tool_id}/preview')
def preview(tool_id: str, payload: Inputs, user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.preview(tool_id, payload.inputs, owner(user))


@router.post('/operations/execute')
def execute(payload: Execution, user=Depends(local_admin), connection: ConnectionContext=Depends(require_local_access),
            service=Depends(get_database_tools)):
    return service.execute(payload.token, payload.confirmation, owner(user), connection.client_ip)


@router.post('/reports/{tool_id}')
def create_report(tool_id: str, payload: Inputs, user=Depends(get_current_user), service=Depends(get_database_tools)):
    return service.start_report(tool_id, payload.inputs, owner(user))


@router.get('/reports/{job_id}')
def report_status(job_id: str, user=Depends(get_current_user), service=Depends(get_database_tools)):
    return service.report(job_id, owner(user))


@router.get('/reports/{job_id}/download')
def download(job_id: str, user=Depends(get_current_user), service=Depends(get_database_tools)):
    path = service.download(job_id, owner(user))
    return FileResponse(path, filename=path.name, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
