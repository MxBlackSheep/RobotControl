"""Bounded JPEG work shared by viewers of the same source frame/quality."""
import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import cv2


def encode_jpeg(frame, scale, quality):
    if scale < 1.0:
        height, width = frame.shape[:2]
        frame = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_LINEAR)
    success, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(encoded).decode('utf-8') if success else None


class FrameEncoder:
    def __init__(self, workers=2):
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="FrameEncoder")
        self._slots = asyncio.Semaphore(workers)
        self._frame_token = None
        self._cache = {}
        self._jobs = set()
        self._closed = False
        self.encodes = 0

    async def encode(self, frame, settings):
        if self._closed:
            return None
        token = (frame.frame_number, frame.timestamp, id(frame.frame))
        if token != self._frame_token:
            self._frame_token = token
            self._cache.clear()
        key = (settings.resolution_scale, settings.jpeg_quality)
        job = self._cache.get(key)
        if job is None:
            # Admission happens before task creation, so cancelled/reconnecting
            # viewers cannot leave an unbounded queue of native encoding jobs.
            await self._slots.acquire()
            if self._closed:
                self._slots.release()
                return None
            job = self._cache.get(key) if token == self._frame_token else None
            if job is not None:
                self._slots.release()
                return await asyncio.shield(job)
            job = asyncio.create_task(self._encode(frame.frame, *key))
            if token == self._frame_token:
                self._cache[key] = job
            self._jobs.add(job)
            job.add_done_callback(self._finished)
        # Cancelling a viewer must not cancel another viewer's shared encoding.
        return await asyncio.shield(job)

    def _finished(self, job):
        self._jobs.discard(job)
        if not job.cancelled():
            job.exception()  # Observe errors even if every viewer disconnected.

    async def _encode(self, frame, scale, quality):
        try:
            self.encodes += 1
            future = asyncio.get_running_loop().run_in_executor(self._executor, encode_jpeg, frame, scale, quality)
            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                # Retain the slot until native work finishes; cancellation cannot
                # otherwise prevent executor queues from growing on reconnects.
                await future
                raise
        finally:
            self._slots.release()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self._jobs:
            await asyncio.gather(*list(self._jobs), return_exceptions=True)
        self._cache.clear()
        self._frame_token = None
        self._executor.shutdown(wait=False, cancel_futures=True)
