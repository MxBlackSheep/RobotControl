# PyHSL status, schedules and alerts

`services/pyhsl_client.py` discovers the local PyHSL service. `services/pyhsl_monitor.py` owns
the background poll every 15 seconds. The app starts and stops that worker.
`GET /api/pyhsl/status` is available remotely to every signed-in role and reads
only its stored result. It never waits for the service or takes a scheduler lock.
Scheduled runs use `scheduling/pyhsl_runner.py`. No Stop, Pause or
Resume route is called, and RobotControl never opens Run Control itself.

Set `ROBOTCONTROL_PYHSL_DATA_DIR` to the PyHSL data folder. Otherwise discovery
uses the `data` field in the install base's `current.json`, falling back to its
`data` folder. The default install base is `C:\PyHSL`.

Each request rereads discovery, verifies the health response's instance ID, then
reads the machine token. Use only that token; never access or use the bootstrap
value. HTTP is restricted to `127.0.0.1` or `localhost`, with connections pinned
to IPv4 loopback and no proxy or redirect handling. Reads time out after two
seconds, except for the review list, which has a 30-second timeout. The monitor
reads that list on the first poll, when run IDs or statuses change, or when more than
two minutes have passed since the last read. It also reads the list on every poll
while the previous review response says `active` is true. This client requires
PyHSL commit `d168577b` or later for run and review lists. See the
[PyHSL API reference](https://github.com/MxBlackSheep/pyhsl/blob/main/docs/API_REFERENCE.md)
and [machine-token permissions](https://github.com/MxBlackSheep/pyhsl/blob/main/docs/OPERATOR_GUIDE.md#what-the-schedulers-machine-token-can-do).

`state` describes the service. A `running` reading means the service answered.
It can answer with the Run Control operator window closed. `run` is the
newest row without a terminal status, shown with its raw status, so an unfamiliar
status never reads as finished. The monitor reports `not_running` if the connection
or discovery file is unavailable, the client cannot open or read the machine-token
file, or the health response fails to match the instance ID in the discovery file.
Timeouts, rejected credentials and other invalid responses produce `unknown`.
Unreachable or older-than-60-second readings never report running or known reviews.
While the review list is active, its cached run IDs and blocked flag remain visible,
but `reviews.known` is false and the reason says the summary is cached.

`pyhsl_run_failed` covers failed, unknown-outcome and reconciliation-required
terminal statuses. `pyhsl_review_required` asks a person to record the Run review
in Run Control. Both use recovery recipients and the shared alert email format.
Only non-machine runs created within the last 24 hours qualify. Machine runs are
owned by the scheduler runner, which sends execution alerts to schedule contacts.
For a failed scheduled execution, history and email show PyHSL's `error_summary`
when supplied, or its `error` otherwise. A required Run review keeps its own note.
Independent run alerts use the same fallback in the Error row and include a
different full error under “Full error” for troubleshooting.
For independently monitored runs, NotificationLog stores the
PyHSL run ID as `execution_id`; any existing record for that run and trigger,
including pending or unsuccessful delivery, suppresses automatic resending.
This avoids duplicate mail after an uncertain send. Inspect the notification log
for delivery failures. With no recipients configured, no record is created.

Local admin and user sessions can validate a protocol's parameters and selected mode
through `POST /api/pyhsl/validate`. On refusal RobotControl returns HTTP 400 with
the service's reason. If the service is unavailable, RobotControl reports that.
The schedule picker uses `GET /api/pyhsl/protocols` with the same access. It lists
unattended protocols from the catalogue and omits entries with a reported problem.

Hamilton's run table names a PyHSL run's method
`<data>\sessions\<session_id>\host\ManagedHost.hsl`. `experiment_runner()` in
`pyhsl_monitor.py` turns that into `runner: 'pyhsl'` plus the protocol ID from the
monitor's last run list with that bridge session ID, or no protocol when none
matches; any other method is `runner: 'venus'`. The path layout is not a PyHSL
contract; if it changes, Overview falls back to showing the method file name.

Remote admin and user sessions can read `/api/pyhsl/deck`,
`/api/pyhsl/monitor.js`, `/api/pyhsl/runs/{run_id}` and its `/report`. Run IDs must
be 32 lowercase hex characters. Unavailable, refused and timed-out reads return 503, 404
and 504; other upstream errors return 502.

Deck and run responses relay the complete upstream JSON bodies unchanged, subject
to the client's machine-token redaction, for PyHSL's Monitoring API view on the Run
page; no field is filtered or derived. Run polling does not request the review list.
RobotControl passes `current.requested_at`, `wait.remaining_seconds` and `server_time`
through to PyHSL's monitor bundle without using them itself.

RobotControl never opens PyHSL's `/api/v1/runs/{id}/events`. Opening it registers
a watcher. With a watcher, a Simulation run holds each completed step until a page
reports that it has drawn the step or the pacing time expires. RobotControl never
sends that acknowledgement.

RobotControl fetches the monitor script from the PyHSL service
after the same discovery and instance verification, without sending the machine
token. It is limited to 5 MiB during the upstream read (502 if exceeded) and served
as `text/plain; charset=utf-8` with `X-Content-Type-Options: nosniff`. The page
inlines it into a sandboxed frame; it cannot be loaded as a script in RobotControl's
origin. The default two-second read timeout also applies to deck and script reads.

HTML reports are limited to 5 MiB during the upstream read (502 if exceeded) and
served with `Content-Security-Policy: sandbox` to disable scripts and isolate origin.

See [PyHSL schedules](scheduling-maintenance-guide.md#pyhsl-schedules) for validation
on save and at dispatch, execution receipts, recovery holds and restart behavior.
The [PyHSL glossary](https://github.com/MxBlackSheep/pyhsl/blob/main/docs/GLOSSARY.md)
defines runs, bridge sessions and Run Control.

Failure cases are listed in the headers of `backend/e2e/pyhsl_client_check.py` and
`backend/e2e/pyhsl_runner_check.py`.
