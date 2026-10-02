# Live view: keyframe hitches over the tunnel (2026-10-02)

Follows `live-view-denoise.md` (#51: level 0 at 15 fps, 400 kbit/s, `atadenoise`, keyframe every
second). **Every number below is a development-PC simulation (i5-12490F in a Hyper-V VM, no camera,
`performance_probe.py`), not the N100 or the real tunnel.**

## Question

The owner watches through the Cloudflare tunnel and finds live view "still a bit laggy". Central
review of the owner's screen recording (`Recording 2026-10-02 222120.mp4`, still scene) saw the
picture change jump about once a second, three of six followed by a 200–270 ms gap; a level-0 encode
of clip 085717 had keyframes of 12.6 kB median against 2.5 kB deltas. Hypothesis: on a thin link each
keyframe holds up the frames behind it. #51's probe reported average fps and delay, not gaps.

## What was added

- **Delivery log** (`StreamingSessionHandler.report_delivery`): one INFO line per viewer per minute
  and at session end, including gaps between acknowledgements (≈ what the viewer sees), hitches,
  round trips, window waits and skips by reason. Fields: `camera-maintenance-guide.md`, "Live view
  delivery log". It answers this question from the real tunnel.
- **`LIVE_STREAMING_CONFIG.keyframe_seconds`** (default 1, today's GOP: 15/7/5 frames per level).
- **`performance_probe.py`**: gap p95/max and hitches per minute (gaps ≥ 2 frame intervals) between
  frames shown in the simulated browser; keyframe and delta sizes; skips and the freeze each caused;
  window waits; `--join-every S` (a second viewer joins anew every S seconds: time to its first
  frame shown); `--keyframe-seconds`.

Method: one viewer plus one re-joining every 2.3 s, 60 s per run, level 0 (15/400 + denoise), owner
clip 085717 and the light-off model (#48's `darken` ×8 of clip 123612, `make_model8.py`). The link
model: frames cross one after another at the link rate, are shown half a round trip later and
acknowledged a full round trip later. It does not model loss, TCP or Cloudflare's own buffering.
Evidence: `test-output/live-view-keyframes/` (`gop_matrix.sh`, `gop_matrix.jsonl` and
`gop_matrix_before_fix.jsonl`, `gop_matrix_table.md`, `plan_tables.md`, `startup_trace*.txt`,
`log_line.txt`).

## Finding 1: each keyframe is a hitch on any link up to 1000 kbit/s

Keyframes are 13.1–13.2 kB (owner) and 14.4 kB (light-off model) against 2.0–3.3 kB deltas. On a
500 kbit/s link one keyframe takes about 210 ms to cross while a frame is due every 67 ms, so the
frames behind it arrive late and then in a burst. Hitches per minute equal keyframes per minute, at
every GOP; with no link limit there are none.

Hitches/min; gap p95/max ms between frames shown; join median/p95 ms (after the start fix below):

| scene | RTT s | link kbit/s | GOP 1 s (today) | GOP 2 s | GOP 3 s |
| --- | --- | --- | --- | --- | --- |
| owner | 0.15 | unlimited | 0; 102/125; 603/1005 | 0; 100/119; 1012/1930 | 0; 97/114; 1104/2330 |
| owner | 0.15 | 1000 | 53; 142/159; 700/1093 | 27; 110/191; 1209/2017 | 16; 84/157; 1191/2382 |
| owner | 0.15 | 600 | 61; 197/243; 764/1171 | 32; 96/233; 1243/2138 | 21; 111/206; 1269/2466 |
| owner | 0.15 | 500 | 61; 222/274; 688/1186 | 30; 99/274; 1209/2092 | 22; 112/243; 1297/2495 |
| owner | 0.3 | 1000 | 56; 142/314; 794/1201 | 22; 95/310; 1184/2081 | 17; 93/308; 1262/2470 |
| owner | 0.3 | 600 | 61; 193/322; 834/1239 | 30; 95/302; 1237/2140 | 20; 88/310; 1332/2537 |
| owner | 0.3 | 500 | 61; 220/290; 872/1276 | 30; 98/296; 1283/2180 | 20; 96/310; 1541/2626 |
| light-off model | 0.15 | 1000 | 60; 158/191; 696/1094 | 30; 95/293; 1284/2108 | 20; 91/306; 1186/2484 |
| | 0.15 | 600 | 64; 214/282; 789/1185 | 34; 112/468; 1342/2184 | 23; 95/538; 1213/2470 |
| | 0.15 | 500 | 80; 236/332; 855/1253 | 43; 126/564; 1387/2218 | 30; 96/579; 1304/2593 |
| | 0.3 | 1000 | 55; 147/278; 763/1175 | 29; 109/325; 1209/2058 | 22; 89/319; 1252/2545 |
| | 0.3 | 600 | 66; 206/432; 847/1252 | 38; 120/466; 1414/2257 | 28; 95/482; 1324/2635 |
| | 0.3 | 500 | 72; 247/454; 876/1293 | 46; 141/563; 1497/2361 | 32; 109/1626; 1328/2606 |

(The p95 gap of about 100 ms with no link limit is the simulation's own timing on Windows; the frame
interval is 67 ms. A hitch is ≥ 133 ms. Owner at 450 kbit/s, 0.15 s: 61/30/21 hitches per minute.)

## Decision: keep one-second keyframes

- A longer GOP makes hitches rarer (≈ 60 → 30 → 20 a minute) but not shorter: the longest gap stays
  160–320 ms on a limited link (owner) and grows in the light-off model, where deltas are larger (2.0 → 3.1 kB at 2 s)
  and the keyframe crosses with more frames queued behind it.
- It doubles the wait to join or to recover from a skip: median 0.6–0.9 s → 1.0–1.5 s, p95
  1.0–1.3 s → 1.9–2.4 s (GOP 2) and 2.3–2.6 s (GOP 3). Skip recovery is the same wait (the next
  keyframe plus its crossing). The documented "join within about a second" would no longer hold.
- When the owner is the only viewer, opening live view or returning to a hidden tab starts the
  encoder, whose first frame is a keyframe, so these waits apply to a second viewer and to skips.

No GOP setting removes the hitches, so `keyframe_seconds` stays 1. The setting lets the owner try
2 (half the hitches, joins up to about 2 s) without a code change if the real log shows hitches matter more.

## Finding 2: a far viewer's first picture froze for a whole GOP (fixed)

`startup_trace_rtt0.3_600k.txt`: the first keyframe after the encoder starts is **29.7 kB** (rate
control has no history; 11.9–13.2 kB afterwards). On 600 kbit/s 0.3 s away it crosses in about
400 ms, so the first acknowledgement returns at 706 ms. Until then the window is its 2-frame floor,
the next frames wait, and at 657 ms the oldest was over the 0.5 s limit: the viewer skipped to the
next keyframe 50 ms before the acknowledgement. It saw one picture, then nothing for 0.7/1.7/2.7 s
(GOP 1/2/3). That is the owner's usual case: the first viewer starts the encoder. In #51's matrix
this showed only as a lower average (14.2–14.7 fps).

**Change:** until a viewer's first acknowledgement, waiting frames are judged against 1 s and 16
frames instead of 0.5 s and 8 (`FIRST_ACK_WAIT_SECONDS`, `FIRST_ACK_WAITING`). Before it the server
knows nothing about the link, so "slower than the stream" cannot be judged. Afterwards the rules
are unchanged; an unacknowledging viewer still gets 2 frames and is ended after 15 s. Cost: at the
start, frames may wait up to 0.5 s longer before a skip, then go out together when the
acknowledgement arrives (`startup_trace_rtt0.3_600k_after.txt`: waited up to 529 ms, no skip).

Before → after, the runs where skips changed (fps shown; skips, longest freeze ms):

| scene | RTT s | link | GOP | before | after |
| --- | --- | --- | --- | --- | --- |
| owner | 0.3 | 600 | 1 / 2 / 3 | 14.7 / 14.5 / 14.2; 1 late (712 / 1737 / 2734) | 14.9; none |
| owner | 0.3 | 500 | 1 / 2 / 3 | 14.7 / 14.5 / 14.2; 1 late (680 / 1691 / 2629) | 14.9; none |
| owner | 0.15 | 450 | 1 / 2 / 3 | 14.7 / 14.5 / 14.2; 1 late (607 / 1623 / 2657) | 14.9; none (GOP 1: 1 replaced) |
| owner | 0.15 | 500 | 3 | 14.2; 1 late (2652) | 14.9; none |
| light-off | 0.15 | 600 | 1 / 2 / 3 | 14.7 / 14.5 / 14.2; 1 late (412 / 1409 / 2389) | 14.9; none |
| light-off | 0.3 | 1000 | 1 / 2 / 3 | 14.7 / 14.5 / 14.2; 1 late (639 / 1643 / 2614) | 14.9–15.0; none |
| light-off | 0.3 | 500 | 2 / 3 | 14.1 / 14.2; 2 / 1 late (1284 / 2276) | 14.7 / 14.5; 1 late (552 / 1626) |

Full list: `plan_tables.md`. "Replaced" (a keyframe arrived while frames still waited) costs at
most the frames before that keyframe.

## Window and skip rule in steady state

With the start fix there were no `late` or `full` skips on any link from 450 to 1000 kbit/s except
one each for the light-off model on 500 kbit/s 0.3 s away at GOP 2 and 3 (the probe does not record
when), and the average wait for the window is 0–6 ms (owner), up to 33 ms (light-off). The window (one round trip of frames,
6 at 0.15 s here) is far below its 256 kB cap; a keyframe and the frames behind it wait in the link,
not on the server, so neither the window nor the 0.5 s rule makes the keyframe burst worse.
Only the start was affected (Finding 2).

## What would remove the hitches (not done)

- **Smaller keyframes**: libopenh264's first keyframe is 2–3 times a normal one, and every keyframe
  is about five deltas. The bundled ffmpeg's libopenh264 has no intra-refresh option (spreading a
  keyframe over several frames) and no keyframe size cap (`ffmpeg -h encoder=libopenh264`;
  `max_nal_size` splits a frame, it does not shrink it). Another encoder or quantizer limits would
  trade picture quality.
- **Smoothing in the browser**: show frames at their capture spacing behind a short buffer
  (~150–250 ms) so a keyframe's late arrival is absorbed. Adds that much delay on every link.
- Either is a separate decision. The real log will show whether hitches occur on the owner's tunnel
  (`hitches` near `keyframes`, small `send_gap`) before anything else changes.

## Not measured

The N100, the real tunnel's rate and round trip, loss and Cloudflare buffering, the browser's decode
and display time, and HTTP/WebSocket set-up time in joins.
