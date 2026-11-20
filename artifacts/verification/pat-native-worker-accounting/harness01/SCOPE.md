# Diagnostic scope

The exact 291-file native supervisor candidate runs its original thirty-case worker and authority-vault test. A harness observer records self/waited-child usage and bounded global pressure at the existing test/launch/reap boundaries. No extra wait, poll, signal, PID-based read, worker case or scheduling change is added. The prior native audit remains intact.

Original bounds remain: 60-second worker, 180-second parent, six parent SQLite opens, 16 MiB file, 256 MiB retained scratch, 8192 files, 8 MiB log, five-second held snapshot and 15 MiB vault. No physical hardware, MCU, inference, external service or acquired controller code runs. Unknown case effects remain unknown; no interrupted case DB may be opened for recovery.

Global pressure is context, not process attribution. Peak RSS is not additive. CPU observations do not establish a wait cause or deadline guarantee. Audit hooks remain cooperative controls rather than an OS sandbox.
