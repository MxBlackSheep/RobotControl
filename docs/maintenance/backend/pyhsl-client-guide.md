# PyHSL status, schedules and alerts

`services/pyhsl_client.py` discovers Run Control; `services/pyhsl_monitor.py` owns
the background poll every 15 seconds. The app starts and stops that worker.
`GET /api/pyhsl/status` is available remotely to every signed-in role and reads
only its stored result. It never waits for Run Control or takes a scheduler lock.
Scheduled runs use `scheduling/pyhsl_runner.py`. No Stop, Pause or
Resume route is called, and RobotControl never opens Run Control itself.

Set `ROBOTCONTROL_PYHSL_DATA_DIR` to the PyHSL data folder. Otherwise discovery
uses the `data` field in the install base's `current.json`, falling back to its
`data` folder. The default install base is `C:\PyHSL`.

Each request rereads discovery, verifies the health response's instance ID, then
reads the machine token. Use only that token; never access or use the bootstrap
value. HTTP is restricted to `127.0.0.1` or `localhost`, with connections pinned
to IPv4 loopback and no proxy or redirect handling. Reads time out after two
seconds, and the review list after 30, because Run Control parses every journal for
it. The monitor reads that list only when a run row changes or every two minutes. A
timeout reads as `unknown`, not as closed. Start uses a 60-second POST timeout.
Before a resend after a failed Start or a restart, RobotControl reads Run Control's
runs and adopts a match. If there is no match, it rechecks the launch guard before
POST and resends the saved request with the execution ID as `request_id`; Run
Control deduplicates it. The guard runs before every Start POST, including after
preparation, and releases its locks before HTTP. A refused send fails the
occurrence with a recovery hold and failure alert.

`state` describes Run Control, not a run: `running` means it answered. `run` is the
newest row without a terminal status, shown with its raw status, so an unfamiliar
status never reads as finished. Connection or discovery absence produces
`not_running`; authentication and invalid responses produce `unknown`.
Unreachable or older-than-60-second readings never report running or known reviews.
While reconciliation is active, its cached run IDs and blocked flag remain visible,
but `reviews.known` is false and the reason says the summary is cached.

`pyhsl_run_failed` covers failed, unknown-outcome and reconciliation-required
terminal statuses. `pyhsl_review_required` asks a person to record the Run review
in Run Control. Both use recovery recipients and the shared alert email format.
Only non-machine runs created within the last 24 hours qualify. Machine runs are
owned by the scheduler runner, which sends execution alerts to schedule contacts.
For independently monitored runs, NotificationLog stores the
PyHSL run ID as `execution_id`; any existing record for that run and trigger,
including pending or unsuccessful delivery, suppresses automatic resending.
This avoids duplicate mail after an uncertain send. Inspect the notification log
for delivery failures. With no recipients configured, no record is created.

`POST /api/pyhsl/validate` requires a local admin or user session. It accepts
`protocol_id`, `parameters` and `mode`, and returns Run Control's Validate payload,
including `protocol.parameters` and `protocol.revision`. Refusals return HTTP 400
with the service's text; absence returns a short unavailable reason. The machine
token can read `/deck` through the Monitoring API; person controls remain unavailable.

`GET /api/pyhsl/protocols` has the same access as Validate. It relays the
`protocols` list of Run Control's `/catalog` (PyHSL's `docs/api/notes.md` states the
contract) and keeps only protocols with `unattended` true and no `problem` (unreadable
or to be imported again; its revision is null), each with `id`, `name`, `revision`,
`modes` and `description`. Archived protocols are not in
the catalogue.

Hamilton's run table names a PyHSL run's method
`<data>\sessions\<session_id>\host\ManagedHost.hsl`. `experiment_runner()` in
`pyhsl_monitor.py` turns that into `runner: 'pyhsl'` plus the protocol ID from the
monitor's last `/runs` read with that `session_id`, or no protocol when none
matches; any other method is `runner: 'venus'`. The path layout is not a PyHSL
contract; if it changes, Overview falls back to showing the method file name.

Remote admin and user sessions can read `/api/pyhsl/deck`,
`/api/pyhsl/monitor.js`, `/api/pyhsl/runs/{run_id}` and its `/report`. Run IDs must
be 32 lowercase hex characters, matching PyHSL's `controller.py` import of
`archive.RUN_FOLDER`. Unavailable, refused and timed-out reads return 503, 404
and 504; other upstream errors return 502.

Deck and run responses relay the complete upstream JSON bodies unchanged, subject
to the client's machine-token redaction, for PyHSL's Monitoring API view on the Run
page; no field is filtered or derived. Run polling does not request reconciliation.

The monitor script is read from Run Control's `/monitor.js`, outside `/api/v1`,
after the same discovery and instance verification, without sending the machine
token. It is limited to 5 MiB during the upstream read (502 if exceeded) and served
as `text/plain; charset=utf-8` with `X-Content-Type-Options: nosniff`. The page
inlines it into a sandboxed frame; it cannot be loaded as a script in RobotControl's
origin. The default two-second read timeout also applies to deck and script reads.

HTML reports are limited to 5 MiB during the upstream read (502 if exceeded) and
served with `Content-Security-Policy: sandbox` to disable scripts and isolate origin.

Saving a PyHSL schedule validates again unless it stays off with its protocol,
parameters and mode unchanged. A PyHSL schedule's mode is `simulation`, `test` or
`real` (a VENUS schedule's is `real` or `simulation`); Validate, on save and at
dispatch, decides which of them the protocol allows, and PyHSL sets VENUS's
Simulation Mode to match before HxRun starts. See
[the scheduling guide](scheduling-maintenance-guide.md#pyhsl-schedules) for the
receipt, gates, review policy and restart behavior.

Failure cases are listed in the headers of `backend/e2e/pyhsl_client_check.py` and
`backend/e2e/pyhsl_runner_check.py`.
