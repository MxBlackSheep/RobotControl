"""Owner-run Windows check: disposable package, Ctrl+Break, one cleanup and playable last clip.
Run in a console: python backend/e2e/packaged_shutdown_check.py <candidate-folder>
Requires a camera. Uses only a relocated package and its disposable video/data directories.
No exit-code-zero expectation. Never run against an installed application folder.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
import cv2
from backend.e2e import packaged_app


def run(candidate):
    with tempfile.TemporaryDirectory(prefix="rc-shutdown-") as directory:
        root=Path(directory)/"relocated"
        shutil.copytree(candidate,root,ignore=shutil.ignore_patterns("data"))
        number=packaged_app.port(8037)
        assert not packaged_app._listeners(number),"Choose a free PACKAGED_E2E_PORT"
        password=secrets.token_urlsafe(24)
        env={**os.environ,"ROBOTCONTROL_ADMIN_PASSWORD":password,
             "ROBOTCONTROL_SCHEDULER_AUTOSTART_DELAY_SECONDS":"disabled",
             "ROBOTCONTROL_AUTO_RECORDING_ENABLED":"false"}
        def request(path,body=None,token=None,method=None):
            headers={"Content-Type":"application/json"}
            if token:headers["Authorization"]="Bearer "+token
            req=urllib.request.Request(f"http://127.0.0.1:{number}"+path,
                data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
            with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
        process=subprocess.Popen([str(root/"RobotControl.exe"),"--host","127.0.0.1","--port",str(number)],
            cwd=root,env=env,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        try:
            packaged_app.wait_until_serving(process,number,lambda:request("/health"))
            token=request("/api/auth/login",{"username":"admin","password":password})["data"]["access_token"]
            def operation(path, body=None, method=None):
                request(path, body or {}, token, method)
                deadline=time.monotonic()+30
                while True:
                    state=request("/api/camera/control-status",token=token)["data"]
                    current=state["health"]["operation"]
                    if current and current["state"] != "pending":
                        assert current["state"]=="succeeded",current
                        return state
                    assert time.monotonic()<deadline,"Camera operation did not finish"
                    time.sleep(.1)
            state=operation("/api/camera/devices/refresh")
            devices=[d for d in state["cameras"] if d.get("device_identity")]
            assert devices,"Attach a disposable-check camera"
            operation("/api/camera/selection", {"device_identity":devices[0]["device_identity"]}, "PATCH")
            operation("/api/camera/recording/start")
            deadline=time.monotonic()+30
            while not list((root/"data/videos/rolling_clips").glob("*.partial.avi")):
                assert time.monotonic()<deadline,"Recording did not start"
                time.sleep(.2)
            time.sleep(3)
            process.send_signal(signal.CTRL_BREAK_EVENT)
            process.wait(timeout=45)
            logs="\n".join(p.read_text(errors="replace") for p in (root/"data/logs").glob("*.log") if "error" not in p.name)
            for name in ("PyHSL monitor","Log readers","Health sampler","Database tools","Resource diagnostics",
                         "Live streaming service","Automatic recording service","Scheduling service","HxRun maintenance enforcer","Camera service"):
                assert logs.count(name+" stopped")==1,name
            assert logs.count("Backend session stopped | ")==1
            clips=[p for p in (root/"data/videos/rolling_clips").iterdir() if p.suffix in (".avi",".mp4") and ".partial." not in p.name]
            assert clips,"No finalized clip"
            cap=cv2.VideoCapture(str(max(clips,key=lambda p:p.stat().st_mtime)))
            try: assert cap.read()[0],"Last clip cannot be played"
            finally:cap.release()
            print("each cleanup once; last clip plays; exit code",process.returncode)
        finally:
            if process.poll() is None:process.kill();process.wait()

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("candidate",type=Path)
    run(parser.parse_args().candidate)
