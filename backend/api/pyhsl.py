"""Cached Run Control status, available to every signed-in role."""
from fastapi import APIRouter, Depends
from backend.services.auth import get_current_user
from backend.services.pyhsl_monitor import get_pyhsl_monitor

router = APIRouter(prefix='/api/pyhsl', tags=['pyhsl'])


@router.get('/status')
async def get_status(current_user: dict = Depends(get_current_user)):
    return get_pyhsl_monitor().status()
