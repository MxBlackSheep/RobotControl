"""Disposable source static routes, unexpected errors, and failed-start cleanup."""
import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock, AsyncMock
from contextlib import ExitStack
import threading
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend import main


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
        assert sorted(stopped)==sorted(["PyHSL","Readers","Tools","Health","Recording","Streaming","Scheduler","Camera","Maintenance"]),stopped
        assert state.shutdown_complete.is_set()
    print("source static, unexpected-error and normal/failed-start cleanup checks passed")

if __name__=="__main__": run()
