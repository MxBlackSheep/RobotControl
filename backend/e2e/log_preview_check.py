"""Disposable log-route contracts and reader/preview text parity.

Growing plain files reuse encoding decisions and read only the tail on the next
poll, with or without an open reader. Truncation/replacement must redetect text;
binary and compressed previews remain refused, and cut first lines are dropped.
"""
import builtins
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
                # A ready reader's decision applies to the prefix of a growing file.
                # Also cover previews without a reader (late bytes still choose cp1252).
                original = path.read_bytes()
                for followed in (path, root / 'preview-only.trc'):
                    if followed != path:
                        followed.write_bytes(original)
                        response = client.get('/api/logfiles/preview', params={
                            'source_id': 'check', 'relative_path': followed.name, 'max_bytes': 13})
                        assert response.json()['data']['content'] == expected, response.text
                    with followed.open('ab') as handle:
                        handle.write(b'next caf\xc3\xa9\n')
                    reads = []
                    class TrackedFile:
                        def __init__(self, handle): self.handle = handle
                        def __enter__(self): return self
                        def __exit__(self, *args): self.handle.close()
                        def __getattr__(self, name): return getattr(self.handle, name)
                        def read(self, size=-1):
                            reads.append((self.handle.tell(), size))
                            return self.handle.read(size)
                    with patch.object(logfiles, 'open', side_effect=lambda *a, **k: TrackedFile(builtins.open(*a, **k)), create=True):
                        response = client.get('/api/logfiles/preview', params={
                            'source_id': 'check', 'relative_path': followed.name, 'max_bytes': 13})
                    assert response.json()['data']['content'] == b'next caf\xc3\xa9\n'.decode('cp1252'), response.text
                    assert reads and all(offset >= followed.stat().st_size - 13 for offset, _ in reads), f'Grown file reread its prefix: {reads}'
                    # A shorter file at the same path is a new encoding decision.
                    followed.write_bytes('fresh caf\u00e9\n'.encode('utf-8'))
                    response = client.get('/api/logfiles/preview', params={
                        'source_id': 'check', 'relative_path': followed.name, 'max_bytes': 100})
                    assert response.json()['data']['content'] == 'fresh caf\u00e9\n', response.text
                    followed.write_bytes(b'price \x80\n' + b' ' * 4)
                    response = client.get('/api/logfiles/preview', params={
                        'source_id': 'check', 'relative_path': followed.name, 'max_bytes': 100})
                    assert response.json()['data']['content'] == 'price \u20ac\n' + ' ' * 4, response.text
                print('grown-file preview reads only the tail; truncation/rewrite redetect encoding', flush=True)
                for suffix in ('.gz', '.zip'):
                    compressed = root / ('compressed' + suffix)
                    compressed.write_bytes(b'not opened')
                    response = client.get('/api/logfiles/preview', params={
                        'source_id': 'check', 'relative_path': compressed.name})
                    assert response.status_code == 400 and 'compressed' in response.text.lower(), response.text
                (root/"binary.log").write_bytes(bytes(range(32))*100)
                response=client.get("/api/logfiles/preview",params={"source_id":"check","relative_path":"binary.log"})
                assert response.json()["data"]["is_binary"] is True,response.text
                print("reader/preview encoding, binary and cut-line checks passed")
        finally:
            manager.close()

if __name__ == "__main__": run()
