# Exact pure retained-history execution scope

Only the named pure method in targets.json. All retained database files are
immutable input bytes; no SQLite connection or runtime opening is allowed.
No network, subprocess, physical/MCU, inference or live-service execution.
Original 180s parent, 16MiB scratch, 8192 files, 256MiB inputs, 16MiB file, 4MiB
JSON and 8MiB logs remain. Preserve all failures, input originals and raw output.
