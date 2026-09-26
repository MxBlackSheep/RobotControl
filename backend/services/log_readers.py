"""Bounded, cancellable log snapshots. Original files are never modified."""
from __future__ import annotations

import codecs
import gzip
import os
import shutil
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path

import psutil

SECTION_BYTES = 1024 * 1024


class ReaderError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def encoding_for(sample: bytes) -> str:
    if sample.startswith(codecs.BOM_UTF8):
        return 'utf-8-sig'
    if sample.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return 'utf-16'
    if sample.count(b'\0') > len(sample) * .08:
        even = sample[::2].count(b'\0')
        odd = sample[1::2].count(b'\0')
        if max(even, odd) > min(even, odd) * 3:
            return 'utf-16-le' if odd > even else 'utf-16-be'
        raise ReaderError('This file contains binary data and cannot be read as text.')
    if b'\0' in sample or sum(byte < 9 or 13 < byte < 32 for byte in sample) > len(sample) * .2:
        raise ReaderError('This file contains binary data and cannot be read as text.')
    try:
        codecs.getincrementaldecoder('utf-8')().decode(sample, final=False)
        return 'utf-8'
    except UnicodeDecodeError:
        return 'cp1252'


@dataclass
class Reading:
    id: str
    owner: str
    source_id: str
    path: Path
    root: Path
    entry: str | None
    snapshot: Path
    state: str = 'preparing'
    error: str | None = None
    encoding: str = ''
    replacement_characters: int = 0
    bytes_scanned: int = 0
    bytes_prepared: int = 0
    sections: list[tuple[int, int, bool]] = field(default_factory=list)
    touched: float = field(default_factory=time.monotonic)
    captured_at: float = field(default_factory=time.time)
    fingerprint: tuple = ()
    cancel: threading.Event = field(default_factory=threading.Event)


class LogReaderManager:
    def __init__(self, directory: Path, *, max_reader_bytes=1024**3,
                 max_total_bytes=2 * 1024**3, idle_seconds=900, section_bytes=SECTION_BYTES):
        self.max_reader_bytes = max_reader_bytes
        self.max_total_bytes = max_total_bytes
        self.idle_seconds = idle_seconds
        self.section_bytes = section_bytes
        directory.mkdir(parents=True, exist_ok=True)
        # Only remove our own orphaned process directories, never another live app's cache.
        for child in directory.glob('reader-process-*'):
            try:
                pid = int(child.name.split('-')[2])
                if not psutil.pid_exists(pid) and child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
            except (ValueError, OSError):
                pass
        self.directory = directory / f'reader-process-{os.getpid()}-{uuid.uuid4().hex}'
        self.directory.mkdir()
        self.lock = threading.RLock()
        self.readers: dict[str, Reading] = {}
        self.total_bytes = 0
        self.slots = threading.BoundedSemaphore(2)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='log-reader')
        self.closed = threading.Event()
        self.janitor = threading.Thread(target=self._expire_loop, daemon=True, name='log-reader-expiry')
        self.janitor.start()

    def create(self, owner, source_id, path: Path, root: Path, entry=None) -> Reading:
        if self.closed.is_set() or not self.slots.acquire(blocking=False):
            raise ReaderError('Two logs are already being prepared. Cancel one or try again shortly.', 429)
        with self.lock:
            if len(self.readers) >= 64:
                self.slots.release()
                raise ReaderError('Too many open log readers. Close an existing reader and retry.', 429)
            ident = uuid.uuid4().hex
            reading = Reading(ident, owner, source_id, path, root, entry, self.directory / f'{ident}.txt')
            self.readers[ident] = reading
            self.pool.submit(self._prepare, reading)
            return reading

    def get(self, ident: str, owner: str) -> Reading:
        with self.lock:
            reading = self.readers.get(ident)
            if reading is None or reading.owner != owner:
                raise ReaderError('Reader expired or is unavailable. Reopen the selected file.', 404)
            if time.monotonic() - reading.touched > self.idle_seconds:
                self.release(ident, owner)
                raise ReaderError('Reader expired. Reopen the selected file.', 404)
            return reading

    def status(self, reading: Reading) -> dict:
        with self.lock:
            changed = False
            if reading.fingerprint:
                try:
                    stat = reading.path.stat()
                    changed = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != reading.fingerprint
                except OSError:
                    changed = True
            return dict(id=reading.id, state=reading.state, error=reading.error,
                        file_path=str(reading.path), entry_path=reading.entry,
                        display_name=Path(reading.entry).name if reading.entry else reading.path.name,
                        compressed=bool(reading.entry or reading.path.suffix.lower() == '.gz'),
                        encoding=reading.encoding, replacement_characters=reading.replacement_characters,
                        bytes_scanned=reading.bytes_scanned, bytes_prepared=reading.bytes_prepared,
                        section_count=len(reading.sections), captured_at=reading.captured_at,
                        source_changed=changed)

    def section(self, reading: Reading, cursor: str) -> dict:
        with self.lock:
            if reading.state != 'ready':
                raise ReaderError(reading.error or 'This log is still being prepared.', 409)
            # Cursors are scoped to this reader; clients never provide arbitrary offsets.
            if cursor == 'first':
                index = 0
            elif cursor == 'last':
                index = len(reading.sections) - 1
            else:
                try:
                    token, value = cursor.split(':')
                    index = int(value)
                    if token != reading.id:
                        raise ValueError()
                except ValueError:
                    raise ReaderError('Invalid section cursor.')
            if index < 0 or index >= len(reading.sections):
                raise ReaderError('Invalid section cursor.')
            offset, length, continued = reading.sections[index]
            with reading.snapshot.open('rb') as stream:
                stream.seek(offset)
                content = stream.read(length).decode('utf-8')
            return dict(content=content, cursor=f'{reading.id}:{index}',
                        previous_cursor=f'{reading.id}:{index-1}' if index else None,
                        next_cursor=f'{reading.id}:{index+1}' if index+1 < len(reading.sections) else None,
                        section_number=index+1,
                        start_byte=offset, end_byte=offset+length, line_continues=continued,
                        **self.status(reading))

    def release(self, ident: str, owner: str):
        with self.lock:
            reading = self.readers.get(ident)
            if reading is None or reading.owner != owner:
                return
            reading.cancel.set()
            del self.readers[ident]
            if reading.state != 'preparing':
                self._discard(reading)

    def _discard(self, reading: Reading):
        with self.lock:
            reading.snapshot.unlink(missing_ok=True)
            self.total_bytes -= reading.bytes_prepared
            reading.bytes_prepared = 0

    def _prepare(self, reading: Reading, fallback: bool = False):
        try:
            reading.path.resolve().relative_to(reading.root.resolve())
            with ExitStack() as stack:
                raw = stack.enter_context(reading.path.open('rb'))
                initial = os.fstat(raw.fileno())
                fingerprint = (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns)
                if fallback and fingerprint != reading.fingerprint:
                    raise ReaderError('File changed while detecting its encoding. Reopen it to try again.')
                reading.fingerprint = fingerprint
                remaining = None
                if reading.entry:
                    archive = stack.enter_context(zipfile.ZipFile(raw))
                    stream = stack.enter_context(archive.open(reading.entry))
                elif reading.path.suffix.lower() == '.gz':
                    stream = stack.enter_context(gzip.GzipFile(fileobj=raw))
                else:
                    stream = raw
                    remaining = initial.st_size
                output = stack.enter_context(reading.snapshot.open('wb'))
                sample = stream.read(min(65536, remaining) if remaining is not None else 65536)
                if remaining is not None:
                    remaining -= len(sample)
                reading.encoding = 'cp1252' if fallback else encoding_for(sample)
                # An ASCII prefix does not establish UTF-8. Validate the entire stream
                # strictly, then restart once as Windows-1252 if later bytes disprove it.
                decoder = codecs.getincrementaldecoder(reading.encoding)(
                    errors='strict' if reading.encoding == 'utf-8' else 'replace')
                pending = b''
                offset = 0
                continuation = False

                def append_section(data: bytes, next_continues: bool):
                    nonlocal offset, continuation
                    with self.lock:
                        if reading.cancel.is_set():
                            raise ReaderError('Reading cancelled.')
                        if reading.bytes_prepared + len(data) > self.max_reader_bytes:
                            raise ReaderError('Log exceeds the 1 GiB reading limit. Use a smaller log file.')
                        if self.total_bytes + len(data) > self.max_total_bytes:
                            raise ReaderError('Temporary log storage is full. Close other readers and retry.')
                        self.total_bytes += len(data)
                        reading.bytes_prepared += len(data)
                    output.write(data)
                    reading.sections.append((offset, len(data), continuation))
                    offset += len(data)
                    continuation = next_continues

                block = sample
                while True:
                    if reading.cancel.is_set():
                        raise ReaderError('Reading cancelled.')
                    reading.bytes_scanned += len(block)
                    text = decoder.decode(block, final=not block)
                    reading.replacement_characters += text.count('\ufffd')
                    pending += text.encode('utf-8')
                    while len(pending) > self.section_bytes:
                        boundary = self.section_bytes
                        while pending[boundary] & 0xC0 == 0x80:
                            boundary -= 1
                        if pending[boundary-1:boundary+1] == b'\r\n':
                            boundary -= 1
                        newline = pending.rfind(b'\n', 0, boundary)
                        if newline >= boundary // 2:
                            boundary = newline + 1
                        segment, pending = pending[:boundary], pending[boundary:]
                        append_section(segment, not segment.endswith(b'\n'))
                    if not block:
                        break
                    amount = min(65536, remaining) if remaining is not None else 65536
                    block = stream.read(amount)
                    if remaining is not None:
                        remaining -= len(block)
                        if not block and remaining:
                            raise ReaderError('File was truncated while reading. Reopen it to try again.')
                append_section(pending, False)
                after = os.fstat(raw.fileno())
                current = reading.path.stat()
                if ((current.st_dev, current.st_ino) != (initial.st_dev, initial.st_ino)
                    or after.st_size < initial.st_size
                    or (after.st_size == initial.st_size and after.st_mtime_ns != initial.st_mtime_ns)
                    or (reading.entry or reading.path.suffix.lower() == '.gz') and
                       (after.st_size, after.st_mtime_ns) != (initial.st_size, initial.st_mtime_ns)):
                    raise ReaderError('File changed while reading. Reopen it to try again.')
            with self.lock:
                if reading.cancel.is_set():
                    self._discard(reading)
                else:
                    reading.state = 'ready'
        except UnicodeDecodeError:
            with self.lock:
                self._discard(reading)
                reading.sections.clear()
                reading.bytes_scanned = 0
                reading.replacement_characters = 0
            self._prepare(reading, fallback=True)
        except Exception as exc:
            with self.lock:
                reading.state = 'error'
                reading.error = str(exc) if isinstance(exc, ReaderError) else f'Unable to prepare log: {exc}'
                self._discard(reading)
        finally:
            if not fallback:
                self.slots.release()

    def _expire_loop(self):
        while not self.closed.wait(30):
            with self.lock:
                expired = [(r.id, r.owner) for r in self.readers.values()
                           if time.monotonic() - r.touched > self.idle_seconds]
            for ident, owner in expired:
                self.release(ident, owner)

    def close(self):
        self.closed.set()
        with self.lock:
            for reading in list(self.readers.values()):
                self.release(reading.id, reading.owner)
        self.pool.shutdown(wait=True, cancel_futures=False)
        self.janitor.join(timeout=2)
        shutil.rmtree(self.directory, ignore_errors=True)
