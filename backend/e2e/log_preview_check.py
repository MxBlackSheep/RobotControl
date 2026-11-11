"""Disposable log-route contracts and reader/preview text parity."""
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.api import logfiles
from backend.services.auth import get_current_user
from backend.services.log_readers import LogReaderManager


def run():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        app = FastAPI()
        app.include_router(logfiles.router)
        app.dependency_overrides[get_current_user] = lambda: {"user_id": "check", "role": "admin"}
        manager = LogReaderManager(root / "cache")
        app.state.log_readers = manager
        client = TestClient(app, client=("127.0.0.1", 5000))
        try:
            with patch.object(logfiles, "LOGFILE_SOURCES", {"check": {"label": "Check", "path": str(root)}}):
                for route, params, code, message in [
                    ("browse", {"source_id":"unknown"},404,"Unknown log source"),
                    ("preview", {"source_id":"unknown","relative_path":"x"},404,"Unknown log source"),
                    ("archive/browse", {"source_id":"unknown","archive_relative_path":"x"},404,"Unknown log source"),
                    ("browse", {"source_id":"check","relative_path":"../x"},400,"Invalid relative path"),
                    ("preview", {"source_id":"check","relative_path":"missing"},404,"File not found"),
                ]:
                    response=client.get("/api/logfiles/"+route,params=params)
                    assert (response.status_code,response.json()["message"]) == (code,message), response.text
                response=client.post("/api/logfiles/readers",json={"source_id":"unknown","relative_path":"x"})
                assert response.status_code==400 and "Unknown source_id" in response.json()["message"]
                print("route contracts passed", flush=True)
                path=root/"late.trc"
                path.write_bytes(b"ascii line\n"*7000+b"price \x80\n"+b"last caf\xc3\xa9\n")
                reader=manager.create("check","check",path,root,None)
                until=time.monotonic()+10
                while reader.state=="preparing" and time.monotonic()<until: time.sleep(.01)
                assert reader.state=="ready", reader.error
                assert reader.encoding=="cp1252"
                response=client.get("/api/logfiles/preview",params={"source_id":"check","relative_path":path.name,"max_bytes":13})
                assert response.status_code==200,response.text
                expected="last caf\xc3\xa9\n".encode("latin1").decode("cp1252")
                assert response.json()["data"]["content"]==expected,response.text
                (root/"binary.log").write_bytes(bytes(range(32))*100)
                response=client.get("/api/logfiles/preview",params={"source_id":"check","relative_path":"binary.log"})
                assert response.json()["data"]["is_binary"] is True,response.text
                print("reader/preview encoding, binary and cut-line checks passed")
        finally:
            manager.close()

if __name__ == "__main__": run()
