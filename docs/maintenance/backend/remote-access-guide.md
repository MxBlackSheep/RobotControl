# Remote access (Cloudflare Tunnel)

RobotControl is used remotely through a Cloudflare Tunnel (`cloudflared`) from the lab's
N100 computer. This guide covers what the tunnel changes, how to configure it and what a
remote session can do.

## What a remote session can do

A request is local only from a browser on the RobotControl computer itself (loopback, no
proxy headers). Everything through the tunnel is remote, by design.

| Remote sessions can | Only on the RobotControl computer |
| --- | --- |
| Overview, robot status, recovery state | Recovery and Resume actions |
| Read schedules, history, calendar | Create, edit, delete schedules; Methods |
| Camera live view and recordings | Create a backup; Restore for non-admins |
| Tables, stored procedures, Data retrieval | Operations, Manage packages, Database settings |
| Logs (admins: RobotControl logs) | Tip tracking and Cytomat edits, HxRun maintenance mode |

Pages list the sections they hide from remote sessions ("On the RobotControl computer
only: …"). The rule lives in `get_connection_context` (`backend/api/dependencies.py`):
a loopback peer carrying `cf-connecting-ip`, `cf-ray`, `true-client-ip`, `x-real-ip`,
`forwarded` or a non-loopback `X-Forwarded-For` entry is remote.

## Tunnel configuration

- Run `cloudflared` as a Windows service on the RobotControl computer
  (`cloudflared service install <token>`), so the tunnel survives sign-out and restarts.
- Point the public hostname at `http://localhost:8005` (the packaged app's port). Use the
  same hostname for the page and the API; the app assumes one origin (no CORS setup).
- WebSockets: on (Network settings). Live view uses `wss://<host>/api/camera/streaming/video/…`.
- Cache: add a Cache Rule "Bypass cache" for `/api/*`. Hashed files under `/assets/` are
  immutable and cache safely; `index.html` is sent `no-cache`.
- Put **Cloudflare Access** in front of the hostname (one-time PIN or the lab's identity
  provider). RobotControl still requires its own sign-in.
- Security level / Bot Fight Mode: exempt `/api/*` from browser challenges (a WAF skip rule).
  A challenge page answers API calls with HTML 403; the app treats that as a connection
  problem and keeps the sign-in, but the request still fails.

## Limits to know

- Cloudflare ends a request after **100 s** (error 524). Backup creation and package
  upload are local-only. Administrators can restore remotely, but a restore can take up to
  10 minutes: through the tunnel the page then reports "Restore outcome unknown" while the
  server continues. Run restores on the RobotControl computer.
- Uploads through Cloudflare are limited to 100 MB per request.
- Remote sign-in is throttled: 5 failed attempts per username, or 20 per address, in 5
  minutes answer 429 with `Retry-After` (`LoginThrottle` in `backend/api/auth.py`). Local
  sign-ins are never throttled. The counters are in memory; a restart clears them.
- The built-in admin password (public in the repository) never signs in remotely: while an
  account still has it, a remote sign-in answers 403 "Change the default password on the robot
  PC before signing in remotely." Sign in on the RobotControl computer, where the app asks for
  a new password, then sign in remotely with that. A wrong password still gets the usual
  "Invalid username or password". Details: authentication guide, lifecycle step 1.
- The packaged app does not publish `/docs`, `/openapi.json`, source maps or the bundle
  report. Development builds keep `/docs`; set `SOURCEMAP=1` for a build with source maps,
  or run `npm --prefix frontend run bundle-analyze` for the bundle report. Never package
  such a build.

## Troubleshooting

| Symptom | Cause and action |
| --- | --- |
| Status bar: "Connection to RobotControl lost · retrying" | Requests fail without a RobotControl answer (tunnel down, 52x, offline). Check `cloudflared` service status and the computer's network. Clears on the next successful request. |
| Sign-in says "The connection to RobotControl was interrupted (530)" | Tunnel not connected (Cloudflare 1033/530). Restart the `cloudflared` service. |
| Sign-in says "(403)" | A Cloudflare challenge or Access policy blocked the API call. Add the WAF skip rule or sign in to Access again (reload the page). |
| "Too many failed sign-in attempts" | Wait for the stated time, or sign in on the RobotControl computer. |
| "Change the default password on the robot PC before signing in remotely." | The account still has the built-in password. Change it on the RobotControl computer (Admin → User accounts, or sign in there and use the dialog that opens). |
| Live view stops after a few seconds | WebSockets disabled on the hostname, or the connection is too slow; see the camera guide. |
| A page shows "This page could not load" | Its file failed to download (connection drop, or the server was upgraded while the page was open). Reload. |
