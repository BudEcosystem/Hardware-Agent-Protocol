# Passed 1-method attempt

[Proof](proof.json), [complete log](attempt/output.log), [terminal result](attempt/result.json).
1methods; 0failures; 0errors;
67.656test seconds and 71.880s harness elapsed, within180s.
All237project/240frozen inputs,6active harness inputs and159external pins remain unchanged;
829actual origins match. Parent ledger opens: 2.
Raw scratch retains 4269files/19309515bytes, with a complete verified copy.

See [validation correction](../../CORRECTION.md), [private fixture correction](../../SETUP-CORRECTION.md)
and [acquisition correction](../../ACQUISITION-CORRECTION.md) for the preserved failures.
No physical device, MCU, inference or live service runs in this scope. A passing
supervisor transport result does not qualify a PAT or enforce aggregate storage.

The [owned-run audit](owned-audit.json) independently matches the durable ledger,
pre-launch input and launch envelope, original lease identity, worker result and
complete output digest. The256-file private code image exactly matches its
source/resource/seven-package inventory, including157dependency files.
[State audit](state-audit.json) finds26states,21activations,11completions,10cancellations,
zero claims and owners. [Storage audit](storage-audit.json) checks53unchanged
databases:52compact case databases and the separate4096-byte-page supervisor ledger.
The test independently inspects all30cases, confirms replay before/after reopen,
and rejects changed same-key input. Supervisor archive semantic qualification
and quota flags remain false; unresolved effects are not inferred from transport.
