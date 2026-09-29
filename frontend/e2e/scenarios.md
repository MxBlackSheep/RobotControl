# Work in progress: failure cases

Before changing behavior, list here how the change could go wrong. Once the checks
exist, move the lasting cases into the header comment of the spec or backend check
that covers them, then delete them from this file. Keep this file short; finished
work stays in Git history, not here.

## Restore failure dialog (`fix/restore-failure-dialog`)

The restore API answers a failed restore with HTTP 200 and `success: false`.

- A `success: false` answer for a managed `.bak` or a browsed `.bck` shows "Restore Started"
  instead of "Restore Failed".
- A failed restore turns on maintenance mode, so the page blocks requests for a minute.
- The failure dialog hides the reason: `message` or `data.error_details` is missing, or an
  empty or generic text is shown instead.
- A failed restore closes the confirmation dialog or clears the selection, so retrying means
  starting over.
- A real success (`success: true`) stops showing "Restore Started" or stops turning on maintenance.
- A non-2xx answer (for example 500 with `detail`) no longer shows its `detail`.
- One click sends the restore request more than once.
