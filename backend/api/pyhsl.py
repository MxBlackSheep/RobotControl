"""Run Control status, read relays and local protocol validation."""
from contextlib import contextmanager
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from backend.api.dependencies import require_local_access
from backend.services.auth import get_current_user
from backend.services.pyhsl_monitor import get_pyhsl_monitor
from backend.services.pyhsl_client import PyHslClient, PyHslError, PyHslUnavailable, PyHslRefusal, PyHslTimeout
from backend.services.scheduling.pyhsl_runner import validate_protocol

router = APIRouter(prefix='/api/pyhsl', tags=['pyhsl'])
REPORT_MAX_BYTES = 5 * 1024 * 1024
MONITOR_MAX_BYTES = 5 * 1024 * 1024


def reader(current_user: dict = Depends(get_current_user)):
    """Admin and user sessions, remote included, may read what Run Control's Run page shows."""
    if current_user.get('role') not in ('admin', 'user'):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    return PyHslClient()


def run_client(run_id: str, client=Depends(reader)):
    # PyHSL controller uses archive.RUN_FOLDER, including lowercase only.
    if not re.fullmatch('[0-9a-f]{32}', run_id):
        raise HTTPException(status_code=400, detail='Invalid PyHSL run ID')
    return client


@contextmanager
def relay_errors():
    try:
        yield
    except PyHslTimeout as exc:
        raise HTTPException(status_code=504, detail=str(exc)[:300]) from None
    except PyHslUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)[:300]) from None
    except PyHslRefusal as exc:
        raise HTTPException(status_code=404, detail=str(exc)[:300]) from None
    except PyHslError as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:300]) from None


@router.get('/monitor.js')
def get_monitor_script(client=Depends(reader)):
    with relay_errors():
        return PlainTextResponse(client.get_monitor_script(max_bytes=MONITOR_MAX_BYTES),
                                 headers={'X-Content-Type-Options': 'nosniff'})


@router.get('/deck')
def get_deck(client=Depends(reader)):
    with relay_errors():
        return client.get('/deck')


@router.get('/runs/{run_id}')
def get_run(run_id: str, client=Depends(run_client)):
    with relay_errors():
        return client.get(f'/runs/{run_id}')


@router.get('/runs/{run_id}/report')
def get_report(run_id: str, client=Depends(run_client)):
    with relay_errors():
        return HTMLResponse(client.get_report(run_id, max_bytes=REPORT_MAX_BYTES),
                            headers={'Content-Security-Policy': 'sandbox'})


@router.get('/status')
async def get_status(current_user: dict = Depends(get_current_user)):
    return get_pyhsl_monitor().status()


def validate_request(data):
    try:
        return validate_protocol(data.get('protocol_id'), data.get('parameters', {}), data.get('mode'))
    except PyHslUnavailable:
        raise HTTPException(status_code=400, detail='PyHSL Run Control is not running') from None
    except PyHslError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.get('/protocols')
def get_protocols(current_user: dict = Depends(get_current_user), connection=Depends(require_local_access)):
    if current_user.get('role') not in ('admin', 'user'):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    with relay_errors():
        # An entry with "problem" cannot be read or must be imported again; its revision is null.
        return [{key: entry.get(key) for key in ('id', 'name', 'revision', 'modes', 'description')}
                for entry in PyHslClient().get('/catalog')['protocols']
                if entry.get('unattended') is True and 'problem' not in entry]


@router.post('/validate')
def validate(data: dict, current_user: dict = Depends(get_current_user), connection=Depends(require_local_access)):
    if current_user.get('role') not in ('admin', 'user'):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    return validate_request(data)
