# Four unchanged configured runtime tests pass

GPIO, PWM, pending reopen/reconciliation and the sixteen-step configured trial
all pass in 45.556 test seconds and 53.871 elapsed seconds. These are unchanged
test methods on the same [frozen candidate](../../implementation01/README.md)
used by the separate [48-test result](../attempt02/README.md).

The original 180-second deadline and 16 MiB scratch limit remain unchanged. All
1,593 raw files totaling9,488,201 bytes are retained and copied, including 1,265
execution records, 308 configuration records and 152 paired checkpoints. All 703
origins match; 215 bytecode reads are refused and no prohibited attempt occurs.
Source, active harness, 159 external pins and compiler/driver receipts remain
stable. The [proof](proof.json) verifies eight exact database paths, 8,374
table-page references and all 8,694 acquired attempt files. Original raw scratch
remains `/tmp/hms-io-conflict-history-conflict4-skxdapm2`.

These checks preserve legacy 0.1 behavior. They are not a full-suite regression,
current-source attestation, physical-device result or PAT qualification. The
[failed combined retention](../attempt01/README.md) remains preserved.
