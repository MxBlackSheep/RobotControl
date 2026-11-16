"""Whether the camera gives a picture: frozen or too few frames. Pure: fed time, samples and counts.

`CameraRuntime._observe` calls `sample` once a second with the frame count, and with a subsampled
picture only when a new frame arrived. Frozen is judged from new frames only, so a camera that
stops sending is `slow` (zero frames), not frozen; the status shows `no_frames` first anyway.
"""
from collections import deque


class PictureCheck:
    """One per camera generation. `problem` is None, "frozen" or "slow"; `confirmed` once the
    picture has been seen to change."""

    def __init__(self, frozen_seconds, slow_fps, slow_seconds):
        self.frozen_seconds, self.slow_fps, self.slow_seconds = frozen_seconds, slow_fps, slow_seconds
        self.previous = None
        self.changed_at = None
        self.new_frame_at = None
        self.confirmed = False
        self.counts = deque()  # (time, frame count) over the last slow_seconds, plus one older entry
        self.fps = None
        self.problem = None
        self.lost_at = None

    def sample(self, now, frames, picture=None):
        """`picture` (any equality-comparable sample) only when a new frame arrived.
        Returns "lost", "back" or None."""
        if picture is not None:
            if picture != self.previous:
                self.confirmed = self.confirmed or self.previous is not None
                self.previous, self.changed_at = picture, now
            self.new_frame_at = now
        self.counts.append((now, frames))
        while len(self.counts) > 1 and now - self.counts[1][0] >= self.slow_seconds:
            self.counts.popleft()
        start, first = self.counts[0]
        self.fps = (frames - first) / (now - start) if now > start else None
        problem = None
        if self.changed_at is not None and self.new_frame_at - self.changed_at >= self.frozen_seconds:
            problem = "frozen"
        elif now - start >= self.slow_seconds and self.fps < self.slow_fps:
            problem = "slow"
        event = "lost" if problem and not self.problem else "back" if self.problem and not problem else None
        if event == "lost":
            # A frozen picture was lost when it stopped changing; a slow one when the window showed it.
            self.lost_at = self.changed_at if problem == "frozen" else now
        self.problem = problem
        return event
