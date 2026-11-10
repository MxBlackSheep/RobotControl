# PyHSL status, schedules and alerts

`services/pyhsl_client.py` discovers Run Control; `services/pyhsl_monitor.py` owns
the background poll every 15 seconds. The app starts and stops that worker.
`GET /api/pyhsl/status` is available remotely to every signed-in role and reads
only its stored result. It never waits for Run Control or takes a scheduler lock.
Scheduled Simulation runs use `scheduling/pyhsl_runner.py`. No Stop, Pause or
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
timeout reads as `unknown`, not as closed. Start uses a 60-second POST timeout. A lost
reply resends the identical request with the execution ID as `request_id`; Run Control
deduplicates it.

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
token cannot use person routes such as the catalogue.

Remote admin and user sessions can read `/api/pyhsl/runs/{run_id}`, its `/journal`
and `/report`. IDs must be 32 lowercase hex characters, matching PyHSL's
`controller.py` import of `archive.RUN_FOLDER`. Unavailable, refused and timed-out
reads return 503, 404 and 504; other upstream errors return 502.

The run response keeps `run_id`, `protocol`, `status`, `host_status`, `mode`,
`completed_count`, `error`, `origin`, `created_at`, `updated_at`, `current`,
`prompt` and `protocol_revision`, plus `requires_review` from the monitor's cached
review state (null when unknown). Run polling does not request reconciliation. The recorded state has all but `origin` and
`protocol_revision` at the top level: those come from `configuration.origin` and
`configuration.protocol.revision`. Mode is reduced to its `mode` value; current
keeps only `operation_id`, `operation` and `status`. Prompt exposes `waiting` and
`text` from its message, without response controls.

Journal pages keep `events` and `next`, with at most 200 requested events. Each
event keeps `revision`, `at`, `event` and `text`, taking up to 300 characters from
details' summary, message or reason. Deck, state and other detail objects are omitted.
HTML reports are limited to 5 MiB during the upstream read (502 if exceeded) and
served with `Content-Security-Policy: sandbox` to disable scripts and isolate origin.

Saving a PyHSL schedule validates again unless it stays off with its protocol,
parameters and mode unchanged. The only allowed mode is in
`PYHSL_ALLOWED_MODES`, currently `simulation`. See
[the scheduling guide](scheduling-maintenance-guide.md#pyhsl-schedules) for the
receipt, gates, review policy and restart behavior.

Failure cases are listed in the headers of `backend/e2e/pyhsl_client_check.py` and
`backend/e2e/pyhsl_runner_check.py`.
