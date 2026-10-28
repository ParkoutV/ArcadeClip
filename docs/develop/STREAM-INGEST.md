# Live stream ingest inspection and repair

## Behavior

The OBS automatic clipping panel records received media while the broadcast is
running. Analysis and clip export begin after the user stops reception or the
broadcast ends.

- RTMP/SRT: FFmpeg listens for the publisher and writes MPEG-TS continuously.
- YouTube: yt-dlp resolves the current broadcast and HLS media URLs, then FFmpeg
  follows the live playlist and writes Matroska continuously. This path does not
  call `inspect_source`, probe DVR history, or call `download_section`.
- A channel target is pinned to the detected video ID during reconnection.
- Ordinary recording starts at the available live edge. It does not include the
  broadcast history before capture starts, and upstream buffering still applies.
- The stop button flushes FFmpeg with `q` before a bounded forced termination.
  A stalled recording is closed after 30 seconds without file growth.
- YouTube connection errors are reported and retried up to three consecutive
  failures. Already recorded parts are kept, and a failed reconnect can finalize
  those parts. A channel explicitly reported as offline remains in start-wait mode.
- Errors and cancellation retain received files for recovery. Direct recordings
  in progress use `.stream-*`; YouTube recordings use `youtube-live-*` under the
  workspace `streams` directory. Reconnection cannot recover media that was never
  received during a network outage.

## Problems repaired

The previous YouTube implementation only polled DVR snapshots and performed a
finite download after stop/end. A transient metadata error could also finalize
the session immediately. That implementation was replaced with live capture.

Direct ingest used forced termination, discarded FFmpeg errors, and had no
watchdog after the first bytes arrived. It now flushes, reports errors, and detects
stalls. Failed validation/merging no longer automatically removes the recording.

The SRT sender address retains the existing 2.5-second latency and adds `linger=5`.
In a local FFmpeg publisher test, the old address retained only approximately
6.32 seconds of a 9-second broadcast at publisher close. With linger enabled it
retained 9.02 seconds. The sender must use the newly displayed address; changing
the receiving application alone cannot change an already configured OBS sender.
See [FFmpeg protocol options](https://ffmpeg.org/ffmpeg-protocols.html#srt) for
latency and linger semantics.

## Validation

`run/verify_stream_ingest.py --tools <directory containing ffmpeg>` publishes test
video and audio over loopback. It checks file growth during the broadcast, stop
completion, and decoded video/audio. Publisher EOF tests also check the recorded
duration against the full nine-second input.

Verified on Windows ARM64 with the bundled FFmpeg:

| Input | Scenario | Result |
| --- | --- | --- |
| RTMP | User stop while publishing | Growing file; A/V decodes |
| RTMP | Publisher EOF | 9.02 seconds; A/V decodes |
| SRT | User stop while publishing | Growing file; A/V decodes |
| SRT | Publisher EOF with linger | 9.02 seconds; A/V decodes |
| HLS | Rolling local playlist, then user stop | Growing file; 48 video frames plus audio; prior six seconds excluded |

Unit tests cover live capture before stop, reconnection, channel pinning, error
reporting, offline-channel waiting, stop during metadata lookup, input selection,
header propagation, stalled recording, direct part merging, and clipping. The UI
test verifies the live path uses the `streams` directory. Translation coverage is
also checked.

Loopback HLS uses HTTP only in the verification harness. Production YouTube
inputs require HTTPS and certificate verification. A real YouTube broadcast URL,
external OBS machine, router/NAT, and a rebuilt installed application have not
been tested as part of this inspection. Existing packaged applications are not
modified by these source changes.
