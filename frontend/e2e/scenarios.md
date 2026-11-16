# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Camera picture check (frozen or slow picture shows as "Camera not giving a picture")

- A frozen picture (camera still delivering frames) or under 1 frame a second keeps showing as
  connected and recording.
- A moving picture, or one frozen for less than `frozen_seconds` (slow: averaged over less than
  `slow_seconds`), is reported as a problem: a false alarm.
- The state does not clear when the picture moves again or the rate recovers, or clears before.
- A manual Reconnect, Stop or camera change keeps the old generation's problem; an old
  generation's samples change the new generation's state.
- Something reconnects by itself (the generation changes without an operation).
- `no_picture` hides `error`, `reconnecting` or `no_frames`, or recording shows as on during it.
- The WARNING or INFO line is missing, repeated every second, or lacks kind, duration, delivered
  fps, frame sequence or generation.
- A frame gap (no new frame) counts as a frozen picture instead of staying `no_frames`.
- The fake-source option changes how the production worker opens the camera.
- Camera page or Overview: `no_picture` does not say "Camera not giving a picture" (with the
  reason on the page), or a good status says it.
