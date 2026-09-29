"""Local administrator review and repair of application SQLite storage."""
import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StrictBool

from backend.api.dependencies import ConnectionContext, require_local_access
from backend.api.scheduling import SafetyRoute
from backend.services.auth import get_current_user
from backend.services.sqlite_health import SQLiteHealthService
from backend.services.sqlite_safety import SafetyConflict
from backend.utils.audit import log_action
from backend.utils.data_paths import get_data_path, get_backups_path

router = APIRouter(prefix='/api/admin/sqlite', tags=['sqlite'], route_class=SafetyRoute)
DatabaseKind = Literal['scheduling', 'authentication']


def service(database):
    name = 'robotcontrol_scheduling.db' if database == 'scheduling' else os.getenv('ROBOTCONTROL_AUTH_DB_FILENAME', 'robotcontrol_auth.db')
    return SQLiteHealthService(get_data_path() / name, database, get_backups_path() / 'sqlite-safety')


def administrator(user=Depends(get_current_user)):
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail='Administrator access required')
    return user


class RepairRequest(BaseModel):
    token: str


class ReconcileRequest(RepairRequest):
    execution_id: str
    note: str
    robot_ready: StrictBool


@router.get('/{database}/preview')
def preview(database: DatabaseKind, user=Depends(administrator), connection: ConnectionContext = Depends(require_local_access)):
    return service(database).preview()


@router.post('/{database}/repair')
def repair(database: DatabaseKind, payload: RepairRequest, user=Depends(administrator),
           connection: ConnectionContext = Depends(require_local_access)):
    actor = user.get('username', 'unknown')
    if database == 'scheduling':
        from backend.services.scheduling import get_scheduler_engine
        scheduler = get_scheduler_engine()
        with scheduler._schedules_lock, scheduler._jobs_lock:
            scheduler._require_robot_absent()
            if scheduler._owned_execution_ids:
                raise SafetyConflict('Wait for the scheduler execution to finish before repairing storage.')
            result = service(database).repair(payload.token, actor)
            scheduler._load_schedules_from_database()
            scheduler._refresh_manual_recovery_state(force=True)
            result['preview'] = service(database).preview()
    else:
        result = service(database).repair(payload.token, actor)
    log_action(actor=actor, action='repair_sqlite', scope=database, client_ip=connection.client_ip,
               success=True, details={'repaired': result['repaired'], 'backup': result['backup']})
    return result


@router.post('/scheduling/reconcile')
def reconcile(payload: ReconcileRequest, user=Depends(administrator), connection: ConnectionContext = Depends(require_local_access)):
    if not payload.robot_ready:
        raise SafetyConflict('Confirm the robot is ready before reconciling the execution.')
    from backend.services.scheduling import get_scheduler_engine
    scheduler = get_scheduler_engine()
    actor = user.get('username', 'unknown')
    with scheduler._schedules_lock, scheduler._jobs_lock:
        scheduler._require_robot_absent()
        if scheduler._owned_execution_ids:
            raise SafetyConflict('Wait for scheduler execution to finish before reconciliation.')
        result = service('scheduling').reconcile_orphan(payload.token, payload.execution_id, actor, payload.note)
        execution = scheduler.run_log_monitor.store.execution(payload.execution_id)
        scheduler.run_log_monitor.finish(payload.execution_id)
        if execution:
            scheduler._running_jobs.discard(execution.schedule_id)
            scheduler._queued_backlog.discard(execution.schedule_id)
            scheduler._queue_runtime.pop(execution.schedule_id, None)
        scheduler._refresh_manual_recovery_state(force=True)
        result['preview'] = service('scheduling').preview()
    log_action(actor=actor, action='reconcile_sqlite_execution', scope='scheduling', client_ip=connection.client_ip,
               success=True, details={'execution_id': payload.execution_id, 'note': payload.note, 'backup': result['backup']})
    return result
