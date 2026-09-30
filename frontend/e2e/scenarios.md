# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Shared robot status (review findings P1, P2)
- Queue says clear at safety revision 8, scheduler says recovery at revision 9: the rail,
  tab and page banner must show the recovery (newer revision wins).
- Either reply reports unhealthy scheduler storage: storage attention shows regardless of
  revision (fail closed).
- Recovery acknowledged but queued jobs still paused (`resume_required`): the attention
  must stay, worded as waiting for Resume, not as a run needing recovery.
- A scheduler reply without `manual_recovery` must not clear a recovery from the queue reply.

## Status bar removed; attention banner and Overview
- With the bar gone, a pending recovery, a Resume hold or unhealthy storage disappears
  from pages other than Scheduling.
- A failed or malformed status read looks like "all clear" on non-Overview pages.
- The phone navigation button (previously inside the bar) disappears.
- Overview's Now running card shows a progress bar stuck at 100 % once a run exceeds the
  user's estimate, or presents the estimate as a promised end time.
- A running job without a known start or estimate shows NaN, "0 min" or a false bar.
- Up next, Instrument health or Recent runs failing to load blanks the whole Overview.
