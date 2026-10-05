# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Phone layout: Overview, System status, Camera live view, shell (fix/phone-layout-priority-pages)

- At 390x844 or 375x667 the Overview first screen does not show the instrument strip, the hold
  (when runs are held) and the Now running state; the strip clips a long state ("Needs attention").
- The strip still shows SQL Server, or Overview still polls system-health only for it.
- System status: the Databases state (e.g. "1 cannot connect") is below the fold on a phone;
  compact metric cards hide CPU/Memory/Disk values or show an unknown value as 0 %.
- Camera live view on a phone: the picture is narrower than the screen, distorted, cropped or
  shrunk by the controls; the page overflows sideways; controls move out of reach or under 44 px;
  fullscreen, stale and reconnect states stop working; tab order no longer follows the screen.
- Inputs below 16 px on touch screens make iOS Safari zoom on focus; tabs and toggle buttons
  under 44 px on touch; a mouse-driven desktop changes size.
- Desktop layouts (1280/1440) change.
