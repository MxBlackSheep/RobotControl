"""Newer auth storage is unchanged; unreadable observation fields take the legacy hold path."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import sqlite3
from unittest.mock import patch
from backend.services.auth_database import AuthDatabase
from backend.services.stored_data import UpgradeStopped
from backend.models import ScheduledExperiment, JobExecution
from backend.services.scheduling.run_log_monitor import RunLogMonitor


def run():
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"auth.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE SchemaMigrations(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)")
            conn.execute("INSERT INTO SchemaMigrations VALUES (99,'future')")
        conn.close()
        before=path.read_bytes()
        with patch("backend.services.auth_database.get_data_path",return_value=Path(directory)):
            try: AuthDatabase("auth.db")
            except UpgradeStopped: pass
            else: raise AssertionError("newer auth database was accepted")
        assert path.read_bytes()==before
        schedule=ScheduledExperiment("s","Fixture",r"C:\fixture.med","once")
        execution=JobExecution("e","s","running")
        monitor=RunLogMonitor.__new__(RunLogMonitor)
        import threading
        monitor._lock=threading.RLock()
        monitor._states={};monitor._activity_clocks={};monitor.clock=lambda:1
        saved=[]
        monitor.manager=SimpleNamespace(get_schedule_by_id=lambda _:schedule)
        for row in ({"execution_id":"e","unknown":True},{"schedule_id":"s"}):
            monitor._states={}
            monitor._store=SimpleNamespace(restore=lambda:[row],unfinished_executions=lambda:[execution],save=saved.append)
            result=monitor.restore()
            assert len(result)==1 and result[0].legacy
            assert "no saved launch association" in result[0].reason
        print("newer auth unchanged; unknown/missing observation fields retained as legacy")

if __name__=="__main__":run()
