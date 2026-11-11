"""Disposable static routes, errors and normal/failed-start cleanup.

A held-open HTTP request must be cancelled so lifespan stop steps finish within
the tray's ten-second deadline. Only service boundaries are fixtures.
"""
import asyncio
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock, AsyncMock
from contextlib import ExitStack
import threading
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import main


async def open_request_shutdown(config):
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    @config.app.get('/held-open')
    async def held_open():
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return {'released': True}

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    server = main.uvicorn.Server(config)
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    writer = None
    try:
        async with asyncio.timeout(5):
            while not server.started:
                await asyncio.sleep(.01)
            _, writer = await asyncio.open_connection('127.0.0.1', listener.getsockname()[1])
            writer.write(b'GET /held-open HTTP/1.1\r\nHost: localhost\r\n\r\n')
            await writer.drain()
            await entered.wait()
        server.should_exit = True
        done, _ = await asyncio.wait([serving], timeout=8)
        assert done, 'Open request prevented lifespan cleanup within the tray deadline'
        await serving
        assert cancelled.is_set(), 'Open request was not cancelled'
        assert config.timeout_graceful_shutdown == 5
        assert config.app.state.shutdown_complete.is_set()
    finally:
        release.set()
        server.should_exit = True
        await asyncio.wait_for(serving, 5)
        if writer:
            writer.close()
            await writer.wait_closed()
        listener.close()


def run():
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)/"dist";root.mkdir()
        (root/"index.html").write_text("fixture page")
        (root/"ok.js").write_text("fixture asset")
        (root.parent/"outside.txt").write_text("must not escape")
        with patch.object(main,"frontend_dist",root,create=True):
            client=TestClient(main.app)
            assert client.get("/scheduling").text=="fixture page"
            assert client.get("/assets/missing.js").status_code==404
            assert client.get("/api/missing").status_code==404
            assert client.get("/%2e%2e%5coutside.txt").status_code==404
            response=client.get("/ok.js")
            assert response.status_code==200
            assert client.get("/ok.js",headers={"if-none-match":response.headers["etag"]}).status_code==304
    app=FastAPI()
    app.add_exception_handler(Exception,main.global_exception_handler)
    @app.get("/fail")
    def fail(): raise RuntimeError("private diagnostic")
    with patch.object(main.logger,"error") as log:
        response=TestClient(app,raise_server_exceptions=False).get("/fail")
        assert response.status_code==500 and response.json()["success"] is False
        assert "private diagnostic" not in response.text
        assert log.call_args.kwargs.get("exc_info")
    for fail_start in (False, True):
        stopped=[]
        def service(name, start_name="start", stop_name="stop"):
            def start():
                if name=="PyHSL" and fail_start: raise RuntimeError("failed start fixture")
            return SimpleNamespace(**{start_name:start, stop_name:lambda:stopped.append(name)})
        state=SimpleNamespace(log_reader_cache=Path(tempfile.gettempdir())/"unused-cache",shutdown_complete=threading.Event())
        application=SimpleNamespace(state=state)
        async def streaming_stop(): stopped.append("Streaming")
        async def scenario():
            try:
                async with main.lifespan(application): pass
            except RuntimeError:
                assert fail_start
        with ExitStack() as stack:
            for name,value in [
                ("backend.services.log_readers.LogReaderManager",lambda _:service("Readers",stop_name="close")),
                ("backend.services.database_tools.get_database_tools",lambda:None),
                ("backend.services.database_tools.close_database_tools",lambda:stopped.append("Tools")),
                ("backend.services.health_sampler.health_sampler",service("Health")),
                ("backend.services.automatic_recording.get_automatic_recording_service",lambda:service("Recording","start_automatic_recording","stop_automatic_recording")),
                ("backend.services.live_streaming.get_live_streaming_service",lambda:SimpleNamespace(stop_service=streaming_stop)),
                ("backend.services.scheduling.get_scheduler_engine",lambda:service("Scheduler")),
                ("backend.services.camera.get_camera_service",lambda:service("Camera",stop_name="shutdown")),
            ]:stack.enter_context(patch(name,value))
            stack.enter_context(patch.object(main,"get_pyhsl_monitor",lambda:service("PyHSL")))
            stack.enter_context(patch.object(main,"get_hxrun_maintenance_service",lambda:service("Maintenance")))
            stack.enter_context(patch.object(main,"_SCHEDULER_AUTOSTART_DELAY_SECONDS",None))
            stack.enter_context(patch.object(main,"_env_flag",return_value=False))
            asyncio.run(scenario())
            if not fail_start:
                stopped.clear()
                fixture_app = FastAPI(lifespan=main.lifespan)
                fixture_app.state.log_reader_cache = state.log_reader_cache
                fixture_app.state.shutdown_complete = threading.Event()
                # Exercise the configuration constructed by the application entry point.
                with patch.object(main, 'app', fixture_app), patch.object(main, 'EMBEDDED_MODE', False), \
                        patch.object(sys, 'argv', ['startup_cleanup_check']), \
                        patch.object(main.uvicorn, 'Server') as constructor:
                    main.main()
                asyncio.run(open_request_shutdown(constructor.call_args.args[0]))
        assert sorted(stopped)==sorted(["PyHSL","Readers","Tools","Health","Recording","Streaming","Scheduler","Camera","Maintenance"]),stopped
        assert state.shutdown_complete.is_set()
    print("source static, unexpected-error and normal/failed-start cleanup checks passed")

if __name__=="__main__": run()
