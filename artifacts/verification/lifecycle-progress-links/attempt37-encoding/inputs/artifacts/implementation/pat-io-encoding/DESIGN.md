# Preserve evidence while encoding it once

The preceding [PWM profile](../pat-io-group-efficiency/PROFILE-ANALYSIS.json)
measured redundant canonical encoding in configured evidence writes and topology
snapshots. This candidate removes two duplicate encodings. It introduces no new
cache, table shortcut, authority decision or storage format.

The base trial writer exposes a private method for storing its already encoded
envelope. The configured writer supplies its existing exact envelope and digest
to that method after the original combined reservation and wall/group check.
The base writer retains its original check before encoding. Reuse lookup,
per-trial limits, group charge, exclusive create, flush, fsync and publication
remain in their original order. Failed writes retain charges and any file bytes;
no reference is published before durable writing succeeds.

Topology object snapshots already produce canonical bounded bytes, reject
unsupported original scalar types, parse a detached tree and inspect its types.
Those bytes can identify the schema memo without encoding the same tree again.
Byte carriers retain their original parse, type rejection and canonicalization.
All graph and authority-dependent checks continue. Inputs and returned trees do
not become trusted deployment evidence.

Nine focused tests cover exact bytes and references, both evidence streams,
inherited profiles, changed inputs, reuse, budget ordering and retained failures.
The original 87 pure methods and actual cutoff, full GPIO and full PWM methods
remain unchanged. The 60s group deadline, all effect/evidence ceilings, 180s
harness limit and 16 MiB scratch ceiling remain unchanged. Passing complete
capture would still leave independent outcomes, trusted setup/run association,
enforced aggregate storage and public qualification unfinished.
