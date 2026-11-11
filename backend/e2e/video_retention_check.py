"""Disposable video retention checks: 121/125 clips keep newest 120, all formats
and sidecars go together, partials survive; 21 archives keep 20; under-limit
trims delete nothing; a clip-less run must not displace 20 real archives.
No camera, installed video folder, HxRun or SQL access.
"""
from collections import deque
from pathlib import Path
import tempfile
import threading
from unittest.mock import patch
from backend.services import storage_manager as storage
from backend.services.clip_transcoder import finalized_clips


def run():
    with tempfile.TemporaryDirectory(prefix="rc-video-retention-") as directory:
        root = Path(directory)
        with patch.object(storage, "VIDEO_PATH", str(root)), patch("backend.utils.data_paths.is_compiled_mode", return_value=False):
            store = storage.StorageManager()
            for index in range(121):
                path = store.rolling_clips_path / f"clip_20260101_{index:06}.avi"
                path.write_bytes(b"clip")
                path.with_suffix(".json").write_text('{"timestamp": "2026-01-01T00:00:00"}')
            # Both formats of the oldest clip must leave together.
            (store.rolling_clips_path / "clip_20260101_000000.mp4").write_bytes(b"mp4")
            partial = store.rolling_clips_path / "clip_unfinished.partial.avi"
            partial.write_bytes(b"partial")
            store.cleanup_rolling_clips()
            assert len(finalized_clips(store.rolling_clips_path)) == 120
            assert not (store.rolling_clips_path / "clip_20260101_000000.json").exists()
            assert partial.exists()
            for index in range(20):
                folder = store.experiments_path / f"archive_{index:02}"
                folder.mkdir()
                (folder / "kept.avi").write_bytes(b"precious footage")
            extra = store.experiments_path / "archive_20"
            extra.mkdir()
            (extra / "kept.avi").write_bytes(b"new footage")
            ordered = sorted(store.experiments_path.iterdir(), key=lambda p: p.stat().st_ctime)
            store.cleanup_experiment_folders()
            assert set(store.experiments_path.iterdir()) == set(ordered[1:])
            before = set(store.experiments_path.iterdir())
            store.archive_experiment_videos("empty", "Empty")
            store.cleanup_experiment_folders()
            assert set(store.experiments_path.iterdir()) == before, "clip-less run displaced real footage"
            store.cleanup_experiment_folders()
            assert set(store.experiments_path.iterdir()) == before
            for index in range(121, 126):
                (store.rolling_clips_path / f"clip_20260101_{index:06}.avi").write_bytes(b"clip")
            store = storage.StorageManager()
            assert len(finalized_clips(store.rolling_clips_path)) == 120, "startup did not trim 125 clips"
    print("PASS disposable video retention")

if __name__ == "__main__":
    run()
