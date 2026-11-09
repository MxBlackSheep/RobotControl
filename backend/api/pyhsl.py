"""Run Control status, filtered read relays and local protocol validation."""
from contextlib import contextmanager
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from backend.api.dependencies import require_local_access
from backend.services.auth import get_current_user
from backend.services.pyhsl_monitor import get_pyhsl_monitor
from backend.services.pyhsl_client import PyHslClient, PyHslError, PyHslUnavailable, PyHslRefusal, PyHslTimeout
from backend.services.scheduling.pyhsl_runner import validate_protocol

router = APIRouter(prefix='/api/pyhsl', tags=['pyhsl'])
REPORT_MAX_BYTES = 5 * 1024 * 1024


def run_client(run_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get('role') not in ('admin', 'user'):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    # PyHSL controller uses archive.RUN_FOLDER, including lowercase only.
    if not re.fullmatch('[0-9a-f]{32}', run_id):
        raise HTTPException(status_code=400, detail='Invalid PyHSL run ID')
    return PyHslClient()


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


@router.get('/runs/{run_id}')
def get_run(run_id: str, client=Depends(run_client)):
    with relay_errors():
        run = client.get(f'/runs/{run_id}')
        result = {key: run.get(key) for key in ('run_id', 'protocol', 'status', 'host_status',
            'mode', 'completed_count', 'error', 'origin', 'created_at', 'updated_at', 'protocol_revision')}
        configuration = run.get('configuration') or {}
        result['origin'] = run.get('origin') or configuration.get('origin')
        result['protocol_revision'] = run.get('protocol_revision') or (configuration.get('protocol') or {}).get('revision')
        if isinstance(result['mode'], dict):
            result['mode'] = result['mode'].get('mode')
        current = run.get('current')
        result['current'] = ({key: current.get(key) for key in ('operation_id', 'operation', 'status')}
                             if current else None)
        prompt = run.get('prompt') or {}
        result['prompt'] = dict(waiting=bool(prompt) and not (prompt.get('answered') or prompt.get('cancelled')),
                                text=prompt.get('message'))
        reviews = get_pyhsl_monitor().status()['reviews']
        result['requires_review'] = run_id in reviews['run_ids'] if reviews['known'] else None
        return result


@router.get('/runs/{run_id}/journal')
def get_journal(run_id: str, after: int = Query(0, ge=0), limit: int = Query(100, ge=1),
                client=Depends(run_client)):
    with relay_errors():
        page = client.get(f'/runs/{run_id}/journal?after={after}&limit={min(limit, 200)}')
        events = []
        for event in page['events']:
            details = event.get('details') or {}
            text = details.get('summary') or details.get('message') or details.get('reason')
            events.append({**{key: event.get(key) for key in ('revision', 'at', 'event')},
                           'text': text[:300] if isinstance(text, str) else None})
        return dict(events=events, next=page['next'])


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


@router.post('/validate')
def validate(data: dict, current_user: dict = Depends(get_current_user), connection=Depends(require_local_access)):
    if current_user.get('role') not in ('admin', 'user'):
        raise HTTPException(status_code=403, detail='Insufficient permissions')
    return validate_request(data)
