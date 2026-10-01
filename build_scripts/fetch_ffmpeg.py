"""Fetch the pinned LGPL ffmpeg.exe used for H.264 live view.

Run once per workspace (the package build also runs it):
    uv run --locked python build_scripts/fetch_ffmpeg.py

The archive is checked against its SHA-256 and cached in build/vendor; ffmpeg.exe and its licence
are extracted to build/vendor/ffmpeg. Never commit them. If the download fails (BtbN prunes old
builds), download the URL below with a resumable tool, put the zip in build/vendor and rerun;
if the release is gone, pin a newer LGPL release-branch build and update the notices.

Licence: this BtbN build is configured with --enable-version3, so ffmpeg is LGPL 3.0. It must
remain the LGPL build: the GPL builds contain x264.
"""
import hashlib
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

RELEASE = "autobuild-2026-09-30-13-08"
ARCHIVE = "ffmpeg-n9.0.2-17-g2a571b6068-win64-lgpl-9.0.zip"
URL = f"https://github.com/BtbN/FFmpeg-Builds/releases/download/{RELEASE}/{ARCHIVE}"
SHA256 = "6b264b9e6019103f601d98c292bd332fd87acf1c5e941ddff4fb71760fe63432"
# FFmpeg source of this build: the release/9.0 branch at commit 2a571b6068.
SOURCE_URL = "https://github.com/FFmpeg/FFmpeg/tree/2a571b6068"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDOR = PROJECT_ROOT / "build" / "vendor"
FFMPEG_DIR = VENDOR / "ffmpeg"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(archive: Path, attempts: int = 20) -> None:
    """Resume with HTTP Range after a dropped or stalled connection (171 MB; links do drop)."""
    partial = archive.with_suffix(".part")
    print(f"Downloading {URL}")
    total = None
    for attempt in range(1, attempts + 1):
        done = partial.stat().st_size if partial.exists() else 0
        if total is not None and done >= total:
            break
        request = urllib.request.Request(URL, headers={"Range": f"bytes={done}-"} if done else {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if done and response.status != 206:
                    done = 0  # The server ignored the range: start again.
                length = int(response.headers.get("Content-Length", 0))
                total = done + length if length else total
                with partial.open("ab" if done else "wb") as output:
                    shutil.copyfileobj(response, output, 1 << 20)
        except OSError as exc:
            print(f"Attempt {attempt}: {exc}; resuming")
            time.sleep(2)
    if total is None or partial.stat().st_size != total:
        raise RuntimeError(f"Download incomplete after {attempts} attempts; {partial} is kept for the next run")
    partial.replace(archive)


def ensure_ffmpeg() -> Path:
    """Return build/vendor/ffmpeg (ffmpeg.exe, LICENSE.txt, BUILD.txt), fetching it if needed."""
    marker = FFMPEG_DIR / "BUILD.txt"
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == ARCHIVE and (FFMPEG_DIR / "ffmpeg.exe").exists():
        return FFMPEG_DIR
    VENDOR.mkdir(parents=True, exist_ok=True)
    archive = VENDOR / ARCHIVE
    if not archive.exists():
        _download(archive)
    actual = _sha256(archive)
    if actual != SHA256:
        archive.unlink()
        raise RuntimeError(f"{ARCHIVE} has SHA-256 {actual}, expected {SHA256}; the corrupt file was removed")
    if FFMPEG_DIR.exists():
        shutil.rmtree(FFMPEG_DIR)
    FFMPEG_DIR.mkdir()
    top = ARCHIVE.removesuffix(".zip")
    with zipfile.ZipFile(archive) as bundle:
        for member, name in ((f"{top}/bin/ffmpeg.exe", "ffmpeg.exe"), (f"{top}/LICENSE.txt", "LICENSE.txt")):
            with bundle.open(member) as source, (FFMPEG_DIR / name).open("wb") as target:
                shutil.copyfileobj(source, target, 1 << 20)
    marker.write_text(ARCHIVE + "\n", encoding="utf-8")
    return FFMPEG_DIR


if __name__ == "__main__":
    try:
        print(ensure_ffmpeg() / "ffmpeg.exe")
    except Exception as exc:
        print(f"Could not provide ffmpeg: {exc}", file=sys.stderr)
        sys.exit(1)
