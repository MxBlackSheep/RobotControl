# PyHSL status and alerts

`services/pyhsl_client.py` discovers Run Control; `services/pyhsl_monitor.py` owns
the background poll every 15 seconds. The app starts and stops that worker.
`GET /api/pyhsl/status` is available remotely to every signed-in role and reads
only its stored result. It never waits for Run Control or takes a scheduler lock.
This integration starts no runs and calls no POST route.

Set `ROBOTCONTROL_PYHSL_DATA_DIR` to the PyHSL data folder. Otherwise discovery
uses the `data` field in the install base's `current.json`, falling back to its
`data` folder. The default install base is `C:\PyHSL`.

Each request rereads discovery, verifies the health response's instance ID, then
reads the machine token. Use only that token; never access or use the bootstrap
value. HTTP is restricted to `127.0.0.1` or `localhost`, with connections pinned
to IPv4 loopback and no proxy or redirect handling. Reads time out after two
seconds. The future runner can use `post`, whose default timeout is 60 seconds;
it must account for an uncertain outcome if a write times out.

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
Only runs created within the last 24 hours qualify. NotificationLog stores the
PyHSL run ID as `execution_id`; any existing record for that run and trigger,
including pending or unsuccessful delivery, suppresses automatic resending.
This avoids duplicate mail after an uncertain send. Inspect the notification log
for delivery failures. With no recipients configured, no record is created.

Verification: `backend/e2e/pyhsl_client_check.py` covers discovery, credentials,
staleness, status handling and restart deduplication with disposable files, a real
HTTP socket and SQLite. `notification_delivery_check.py` covers both new emails
through local SMTP, including their text and HTML. These checks and the existing
notification tests passed using the existing Python environment; dependency sync
was unavailable. No real PyHSL instance, Hamilton data or instrument was exercised.
