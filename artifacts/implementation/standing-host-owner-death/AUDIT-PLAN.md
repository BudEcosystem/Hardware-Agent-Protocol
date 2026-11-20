# Retained-data audit review plan

Status: audit source prepared, not executed. The root-observed original run passed
all thirteen fixed cases, with39 inner reaps and one outer reap. The287 reviewed
inputs and original attempt remain unchanged. audit_retained.py is a new,
standalone stdlib-only reader; it imports no candidate module, executes no child,
sends no signal, and reruns neither controls nor original qualification.

After source review, run the fixed audit with assertions enabled. It reads the
retained attempt and original sealed inputs, opens only the closed final databases
using SQLite mode=ro/immutable=1 after requiring no journal/WAL/SHM sidecar, reads
/proc identities without signaling, and exclusively creates a new root AUDIT.json.
Existing audit output is never overwritten. An assertion/error means audit failure;
there is no fallback result or reduced matrix.

The audit independently requires:

- Exact ordered thirteen cuts; correct possible/prepared/reply classifications;
  canonical row bytes, original request/deployment hashes, wire references,
  immutable outbox/body/key/sequence identities and original installed selection.
- Keyed mutation/activation/version/episode records, raw response joins, synthetic
  completed activation bytes and zero-output loss witness; exact final database
  agreement with retained snapshots. Immediate reopen changes only the specified
  epoch/revision/recovery fields, with exact next values.
- Original replay's read-only outgoing prefix, consistent opcode/body/hash and
  full transmit/receive accounting; only the case-specific newly requested effect
  suffix, joined to an accepted distinct outbox. Unknown originals never retry.
- Native counters unchanged through owner death and read-only recovery; exact
  new-action results; terminal-prefix/witness plus same-boot empty descriptor and
  retained fences before accepting lost-RETIRE recovery. Claim release is checked
  against actual final database rows, not a status label.
- Every original start identity, SIGKILL/clean-exit classification and exact39+1
  reap family; empty successful child logs, owner closure, original limits and
  observed command deadline. /proc checks require the historic identity absent,
  including zombies; a recycled numeric PID is distinguished by startTicks.
- Exact frozen/current source and interpreter joins; every sealed parent input,
  public244 baseline and copied provenance; original qualifier absolute root,
  reservation/receipt/run identity and actual12/638 output. No generated evidence
  substitutes for that original attempt.

The output records the complete attempt-file inventory and observed identity
absence as audit-time evidence. It remains narrow: no full-host qualification,
physical/public eligibility, protected capacity or universal containment claim.
Root will inspect the source before authorizing this audit; preparing this file
and the draft result/next notes did not execute it.
