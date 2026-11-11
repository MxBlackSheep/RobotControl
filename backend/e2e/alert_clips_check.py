"""Alert clip selection excludes partial files, prefers one format, and takes
three newest finished clips from the shared store. Disposable files only.
"""
from pathlib import Path
import tempfile
from unittest.mock import patch
from backend.services.notifications import SchedulingNotificationService
from backend.services import storage_manager as storage

def run():
    with tempfile.TemporaryDirectory(prefix='rc-alert-clips-') as directory:
        root = Path(directory)
        with patch.object(storage, 'VIDEO_PATH', str(root)), patch('backend.utils.data_paths.is_compiled_mode', return_value=False):
            store = storage.StorageManager()
            names = [f'clip_20261111_12000{i}.avi' for i in range(4)]
            for name in names + ['clip_20261111_120003.mp4', 'clip_20261111_120004.partial.avi']:
                (store.rolling_clips_path / name).write_bytes(b'clip')
            service = SchedulingNotificationService.__new__(SchedulingNotificationService)
            service._rolling_clips_dir = store.rolling_clips_path
            with patch.object(storage, 'get_storage_manager', return_value=store):
                selected = service._collect_recent_rolling_clips(limit=3)
            assert [p.name for p in selected] == [
                'clip_20261111_120003.mp4', 'clip_20261111_120002.avi', 'clip_20261111_120001.avi']
    print('PASS alert finished clip selection')

if __name__ == '__main__':
    run()
