# Labware background-read and edit failures

Recorded before the shared snapshot API change. Verify through the browser with disposable intercepted GET/PUT responses; no unit tests.

- A delayed background GET can finish after a user starts selecting tips or editing a shelf, but before React's pause effect runs. Its result must be invalidated synchronously at the start of editing so it cannot overwrite the captured saved state or newer drafts.
- An unchanged poll must retain the same rack nodes, size, position, keyboard focus and available editing controls. Loading feedback must not insert/remove space above the rack or pulse a focused tip.
- Starting an edit during a read must work; background-read state must not disable the selector or discard the user's first corner.
- Canceling a selection or closing a shelf editor without a draft must resume reading. A no-op command must not leave reading stopped indefinitely.
- Pending drafts and writes must still pause reading, protect failed-save drafts and invalidate late responses. Saving or discarding the last draft resumes reading.
- Repeat on a desktop, a short window and the phone rack dialog. Preserve physical rack order, Cytomat 1–7 order and unavailable/unused positions.
- On a 4K canvas, the Labware heading and toolbar must start on the same bounded content column; a full-width heading beside a separately centered workspace creates disconnected alignment. Switching to Cytomat should bound the whole shelf workspace, including heading/actions, together.
