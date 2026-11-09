"""Cached Run Control status, available to every signed-in role."""
from fastapi import APIRouter, Depends, HTTPException
from backend.api.dependencies import require_local_access
from backend.services.auth import get_current_user
from backend.services.pyhsl_monitor import get_pyhsl_monitor
from backend.services.pyhsl_client import PyHslError, PyHslUnavailable
from backend.services.scheduling.pyhsl_runner import validate_protocol

router = APIRouter(prefix='/api/pyhsl', tags=['pyhsl'])


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
