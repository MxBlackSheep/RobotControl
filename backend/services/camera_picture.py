"""Whether the camera gives a picture: frozen or too few frames. Pure: fed time, samples and counts.

`CameraRuntime._observe` feeds one subsampled frame per second, only when a new frame arrived, so
a gap in frames stays `no_frames` and is not also called frozen.
"""
from collections import deque


class PictureCheck:
    """One per camera generation. `problem` is None, "frozen" or "slow"."""

    def __init__(self, frozen_seconds, slow_fps, slow_seconds):
        self.frozen_seconds, self.slow_fps, self.slow_seconds = frozen_seconds, slow_fps, slow_seconds
        self.previous = None
        self.changed_at = None
        self.counts = deque()  # (time, frame count), spanning at least slow_seconds once available
        self.fps = None
        self.problem = None
        self.lost_at = None

    def sample(self, now, picture, frames):
        """`picture` is any equality-comparable sample. Returns "lost", "back" or None."""
        if picture != self.previous:
            self.previous, self.changed_at = picture, now
        self.counts.append((now, frames))
        while len(self.counts) > 1 and now - self.counts[1][0] >= self.slow_seconds:
            self.counts.popleft()
        start, first = self.counts[0]
        self.fps = (frames - first) / (now - start) if now > start else None
        problem = None
        if now - self.changed_at >= self.frozen_seconds:
            problem = "frozen"
        elif now - start >= self.slow_seconds and self.fps < self.slow_fps:
            problem = "slow"
        event = "lost" if problem and not self.problem else "back" if self.problem and not problem else None
        if event == "lost":
            # A frozen picture was lost when it stopped changing; a slow one when the window showed it.
            self.lost_at = self.changed_at if problem == "frozen" else now
        self.problem = problem
        return event
