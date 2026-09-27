"""Authenticated public interface; never accepts SQL or Python entry points."""
from typing import Any, Literal
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from backend.api.dependencies import require_local_access, ConnectionContext
from backend.services.auth import get_current_user
from backend.services.database_tools import get_database_tools
from backend.services.database_packages import MAX_UPLOAD, PackageError
from backend.utils.audit import log_action


class ToolRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()
        async def handler(request):
            if request.method == 'POST' and request.url.path.endswith('/packages'):
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
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        return handler


router = APIRouter(prefix='/api/database/tools', tags=['database'], route_class=ToolRoute,
                   dependencies=[Depends(get_current_user)])


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
def catalogue(kind: Literal['operation', 'report'], user=Depends(get_current_user), service=Depends(get_database_tools)):
    if kind == 'operation' and user.get('role') != 'admin':
        return []
    return service.catalogue.tools(kind)


@router.get('/experiments')
def experiments(search: str = Query('', max_length=200), page: int = Query(1, ge=1), service=Depends(get_database_tools)):
    result = service.database.get_table_data('Experiments', limit=25, offset=(page-1)*25,
                                            search=search, order_by='ExperimentID', sort_direction='desc')
    return dict(rows=result.rows, total_count=result.total_count)


@router.get('/packages')
def packages(user=Depends(local_admin), service=Depends(get_database_tools)):
    return service.catalogue.packages()


@router.post('/packages')
def install(file: UploadFile = File(...), user=Depends(local_admin),
            connection: ConnectionContext=Depends(require_local_access), service=Depends(get_database_tools)):
    try:
        result = service.catalogue.install(file.file.read(MAX_UPLOAD+1))
        log_action(actor=owner(user), action='install_database_package', scope='database', client_ip=connection.client_ip,
                   success=True, details=dict(package=result['id'], version=result['version']))
        return result
    finally:
        file.file.close()


@router.delete('/packages/{package_id}')
def remove(package_id: str, user=Depends(local_admin),
           connection: ConnectionContext=Depends(require_local_access), service=Depends(get_database_tools)):
    service.catalogue.remove(package_id)
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
