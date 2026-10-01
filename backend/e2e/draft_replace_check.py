"""Draft writes survive another program briefly opening the draft file (Windows).

Run: uv run --locked python -m backend.e2e.draft_replace_check [--stress N]
No SQL Server; uses a disposable data folder.

Failure cases:
- A scanner or indexer has the draft JSON open, sharing delete, while the draft is saved
  or its trial cleared: the write must succeed with the new revision. A legacy replace
  (MoveFileEx) fails here with WinError 5, which made Try fail intermittently.
- A program has the draft open without sharing delete: the save fails with an error and
  the previous revision stays intact and readable.
- --stress N: N consecutive saves of one draft. Any failure means a program outside
  RobotControl still breaks draft replacement on this machine.
"""
import argparse
from contextlib import contextmanager, nullcontext
import ctypes
import ctypes.wintypes as wt
import json
import os
from pathlib import Path
import tempfile
import time
import traceback

from backend.services.database_tools import DatabaseTools
from backend.services.report_authoring import ReportDraft

ROOT = Path(__file__).resolve().parents[2]
SHARE_READ_WRITE, SHARE_ALL = 0x3, 0x7
kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.CreateFileW.restype = wt.HANDLE
kernel32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]


@contextmanager
def held(path, share):
    """Keep the file open for reading, as another program would."""
    handle = kernel32.CreateFileW(str(path), 0x80000000, share, None, 3, 0x80, None)
    if handle == wt.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        kernel32.CloseHandle(handle)


def run(stress):
    evidence = Path(os.environ.get('ROBOTCONTROL_E2E_EVIDENCE', ROOT/'test-output/draft-replace-verification'))
    evidence.mkdir(parents=True, exist_ok=True)
    result = dict(command='uv run --locked python -m backend.e2e.draft_replace_check' + (f' --stress {stress}' if stress else ''),
                  checks=[], passed=False)
    try:
        with tempfile.TemporaryDirectory(prefix='rc-draft-replace-') as temp:
            service = DatabaseTools(Path(temp)/'tools', ROOT/'database_packages', database=object(), guard=nullcontext)
            try:
                authoring = service.authoring
                def save(record, **patch):
                    draft = ReportDraft.model_validate({**record['draft'], **patch})
                    return authoring.save(draft, 'admin', record['id'], record['revision'])
                saved = authoring.save(ReportDraft(name='Replace check'), 'admin')
                path = authoring._path(saved['id'])
                with held(path, SHARE_ALL):
                    saved = save(saved, name='Saved while scanned')
                    authoring.clear_trial(saved['id'], 'admin')
                current = authoring.get(saved['id'], 'admin')
                assert current['revision'] == 2 and current['draft']['name'] == 'Saved while scanned', current
                result['checks'].append('Save and trial reset succeed while another program has the draft open sharing delete')
                with held(path, SHARE_READ_WRITE):
                    try:
                        save(saved, name='Must not replace')
                        raise AssertionError('A draft held without sharing delete was replaced')
                    except OSError as exc:
                        result['exclusive_holder_error'] = str(exc)
                assert authoring.get(saved['id'], 'admin') == current
                result['checks'].append('A holder that forbids deletion gets an error; the previous revision stays intact')
                if stress:
                    failures, start = [], time.monotonic()
                    for index in range(stress):
                        try:
                            saved = save(saved, change_note=str(index))
                        except OSError as exc:
                            failures.append(dict(index=index, error=str(exc)))
                    result['stress'] = dict(saves=stress, failures=len(failures), first=failures[:3],
                                            seconds=round(time.monotonic() - start, 1))
                    assert not failures, result['stress']
                    result['checks'].append(f'{stress} consecutive saves of one draft without a failed replacement')
                result['passed'] = True
            finally:
                service.close()
    except Exception:
        result['failure'] = traceback.format_exc()
    (evidence/'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stress', type=int, default=0)
    run(parser.parse_args().stress)
