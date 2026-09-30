"""Disposable HTTP/browser fixture. Starts no production app, SQL or robot services."""
import asyncio
import base64
import gzip
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw
from backend.api import logfiles
from backend.services.auth import get_current_user

temporary = tempfile.TemporaryDirectory(prefix='viewer-e2e-')
fixture = Path(temporary.name)
logs = fixture / 'data' / 'logs'
history = logs / 'history'
history.mkdir(parents=True)
content = 'START-MARKER\r\n' + ('Robot observation αβγ 中文 😀\r\n' * 45000) + ('L' * (1024*1024+7)) + '\r\nEND-MARKER\r\n'
files = []
for name, encoding in [('unicode.log', 'utf-8'), ('utf16.log', 'utf-16')]:
    raw = content.encode(encoding)
    (history / name).write_bytes(raw)
    (history / (name+'.gz')).write_bytes(gzip.compress(raw))
    for path in [f'history/{name}', f'history/{name}.gz']:
        files.append(dict(path=path, entry=None, sha256=hashlib.sha256(content.encode()).hexdigest()))
with zipfile.ZipFile(history / 'logs.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('nested/unicode.log', content)
files.append(dict(path='history/logs.zip', entry='nested/unicode.log', sha256=hashlib.sha256(content.encode()).hexdigest()))
ansi = 'ASCII prefix\r\n' * 90000 + 'café\r\n'
(history / 'legacy.log.gz').write_bytes(gzip.compress(ansi.encode('cp1252')))
files.append(dict(path='history/legacy.log.gz',entry=None,sha256=hashlib.sha256(ansi.encode()).hexdigest()))
(history / 'corrupt.gz').write_bytes(b'not gzip')
(logs / 'robotcontrol_backend.log').write_text('ACTIVE-START\nCurrent log\nACTIVE-END\n', encoding='utf-8')
evidence = ROOT / 'test-output' / 'viewer-verification'
evidence.mkdir(parents=True, exist_ok=True)
(evidence / 'fixture-manifest.json').write_text(json.dumps(dict(files=files, temporary_root=str(fixture)), indent=2))
camera = dict(width=640, height=480, send_frames=True, disconnect=False, generation='g1')


@asynccontextmanager
async def lifespan(app):
    yield
    if getattr(app.state, 'log_readers', None):
        app.state.log_readers.close()
    if getattr(app.state, "database_tools", None):
        app.state.database_tools.close()
    temporary.cleanup()


app = FastAPI(lifespan=lifespan)
app.state.log_root = logs
app.state.log_reader_cache = fixture / 'cache'
logfiles.LOGFILE_SOURCES['python_log']['path'] = str(logs)
logfiles.LOGFILE_SOURCES['hamilton_logfiles']['path'] = str(logs)


def user(request: Request):
    token = request.headers.get('authorization', '').removeprefix('Bearer ')
    if token not in {'viewer-admin', 'other-admin', 'viewer-user', 'e2e-admin'}:
        raise HTTPException(401)
    return dict(user_id=token, username=token, role='user' if token == 'viewer-user' else 'admin', session=dict(is_local=False))


app.dependency_overrides[get_current_user] = user
app.include_router(logfiles.router)


@app.middleware('http')
async def fixture_peer(request: Request, call_next):
    # Exercise the real connection classifier with a simulated remote TCP peer.
    if request.headers.get('x-e2e-peer'):
        request.scope['client'] = (request.headers['x-e2e-peer'], 12345)
    return await call_next(request)


@app.get('/api/auth/me')
def me(request: Request):
    return dict(success=True, data=user(request))


@app.get('/__e2e/health')
def health(): return dict(ready=True)


@app.post('/__e2e/shutdown')
def shutdown():
    camera['disconnect'] = True
    app.state.server.should_exit = True
    return dict(stopping=True)


@app.get('/__e2e/manifest')
def manifest(): return dict(files=files)


@app.post('/__e2e/readers')
async def reader_control(request: Request):
    body = await request.json()
    manager = logfiles._reader_manager(request)
    if body.get('reset'):
        for reader in list(manager.readers.values()): manager.release(reader.id, reader.owner)
        manager.max_reader_bytes = 1024**3
        manager.max_total_bytes = 2*1024**3
        manager.idle_seconds = 900
    if 'max_reader_bytes' in body: manager.max_reader_bytes=body['max_reader_bytes']
    if 'max_total_bytes' in body: manager.max_total_bytes=body['max_total_bytes']
    if body.get('expire'):
        manager.readers[body['expire']].touched = 0
    if body.get('append'): (logs/'robotcontrol_backend.log').open('a').write('APPENDED\n')
    return dict(readers=len(manager.readers), cache_bytes=manager.total_bytes)


@app.post('/__e2e/camera')
async def set_camera(request: Request):
    camera.update(await request.json())
    return camera


@app.get('/api/camera/control-status')
def camera_status():
    return dict(data=dict(cameras=[dict(id=0,name='Fixture camera',device_identity='fixture-camera')],
        health=dict(device_identity='fixture-camera',generation=camera['generation'],capture_state='connected',
        recording_state='recording',recording_requested=True,last_frame_age_seconds=0,error=None,operation=None)))


@app.get('/api/camera/streaming/status')
def streaming_status(): return dict(data=dict(status=dict(enabled=True, active_session_count=0,max_sessions=4)))


@app.post('/api/camera/streaming/session')
def create_session():
    camera['disconnect']=False
    return dict(data=dict(session_id='fixture-session',websocket_state='connecting',is_active=True))


@app.delete('/api/camera/streaming/session/{ident}')
def delete_session(ident: str): return dict(success=True)


@app.websocket('/api/camera/streaming/video/{ident}')
async def video(ws: WebSocket, ident: str):
    await ws.accept()
    try:
        while True:
            if camera['disconnect']:
                await ws.close()
                return
            if camera['send_frames']:
                width, height = camera['width'], camera['height']
                frame = Image.new('RGB',(width,height),'#244d6b')
                draw = ImageDraw.Draw(frame)
                for (x,y), color in zip([(0,0),(width-40,0),(0,height-40),(width-40,height-40)],['red','lime','yellow','magenta']):
                    draw.rectangle((x,y,x+39,y+39),fill=color)
                draw.text((width//2,height//2),f'{width} x {height}',fill='white')
                output=io.BytesIO();frame.save(output,format='JPEG')
                await ws.send_json(dict(type='frame',data=base64.b64encode(output.getvalue()).decode()))
            await asyncio.sleep(.2)
    except Exception:
        pass


from backend.api.database_tools import router as database_tools_router, get_lab_settings
from backend.services.database_tools import DatabaseTools, get_database_tools
from backend.e2e.database_fixture import DatabaseFixture, configure_fixture_report_sources, configure_fixture_lab_settings
app.state.database_tools = DatabaseTools(fixture / 'database-tools', ROOT / 'database_packages', DatabaseFixture(fixture))
configure_fixture_report_sources(app.state.database_tools)
app.state.database_tools.guard = app.state.database_tools.database.guard
app.state.lab_settings = configure_fixture_lab_settings(app.state.database_tools, fixture / 'lab')
app.dependency_overrides[get_lab_settings] = lambda: app.state.lab_settings
app.dependency_overrides[get_database_tools] = lambda: app.state.database_tools
app.include_router(database_tools_router)


# Same envelope as backend/api/scheduling.py; an idle scheduler with no recovery.
@app.get('/api/scheduling/status/queue')
def queue_status():
    return dict(success=True, data=dict(
        queue=dict(queue_size=0, queued_jobs=0, running_jobs=0, max_parallel_jobs=1, capacity_available=True,
                   running_job_details=[], queued_job_details=[], execution_windows=[], hamilton_available=True),
        hamilton=dict(is_running=False, process_count=0, availability='available', last_check='2026-09-30T12:00:00'),
        manual_recovery=dict(active=False, safety_revision=1, storage_healthy=True, pending_recoveries=[])))


@app.get('/api/scheduling/status/scheduler')
def scheduler_status():
    return dict(success=True, data=dict(is_running=True, manual_recovery=None))


@app.get('/api/{path:path}')
def extra_api(path: str):
    return dict(success=True,data=dict(active=False,maintenance_mode=False,experiment_folders=[]))


@app.get('/{path:path}')
def frontend(path: str):
    root=(ROOT/'frontend/dist').resolve()
    target=(root/path).resolve()
    if not target.is_relative_to(root): raise HTTPException(404)
    return FileResponse(target if target.is_file() else root/'index.html')


if __name__ == '__main__':
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8016, log_level='warning', proxy_headers=False, timeout_graceful_shutdown=3))
    app.state.server = server
    server.run()
