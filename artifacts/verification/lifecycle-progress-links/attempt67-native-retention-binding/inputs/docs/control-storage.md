# Control storage for devices, drivers and the intelligence hub

The [in-process metadata binding](../artifacts/verification/pat-native-retention-binding/README.md)
now passes 43 production-build controls, 20 separately instrumented controls and
three syscall scopes, including real descriptor pressure and signal cleanup.
It strengthens directory checks but remains isolated. It neither enforces a hard
disk quota nor completes protected control capacity or actual-worker import.

Status: required design, with bounded SQLite observations, 2026-11-08. The current
runtime does not yet implement protected control capacity or a qualified aggregate
quota provider. [Review and evidence](../artifacts/verification/pat-storage-capacity/README.md).

The first [independent vault candidate](../artifacts/implementation/pat-evidence-vault/README.md)
now implements bounded immutable manifests and owner-held current read snapshots
in a separate database. All 22 distinct methods have passing receipts, with the
original failed scopes retained. It preserves the complete retained I/O dataset
under a 15 MiB vault cap. The [authority-publication candidate](../artifacts/implementation/pat-vault-authority/README.md)
now connects administrator-owned installation, durable original import intents,
the existing semantic reducer and atomic reference publication under a held
snapshot. All [25 selected current-production controls](../artifacts/verification/pat-vault-authority-controls/README.md)
pass in separate scopes. Actual-run validation through this profile remains
incomplete; no physical capacity reservation or public mount is supplied.
The [fresh actual trial](../artifacts/implementation/pat-vault-original-run/README.md)
reached its original worker deadline before import and left the installed vault
empty. It supplies no complete actual-run qualification for this profile.

The [subsequent worker diagnostic](../artifacts/verification/pat-vault-worker-profile/README.md)
also stops before import. Its source databases and retained bytes pass a read-only
audit; the partial worker databases remain unopened. Profiling supplies an
optimization lead, not a passing vault-import or capacity result.

A [subsequent pure validator comparison](../artifacts/verification/pat-validation-walk-evaluation/README.md)
passes 468 differential cases but yields insufficient timing evidence for adoption.
It changes neither the storage profile nor the actual-run qualification status.

The [topology/proof-build candidate](../artifacts/implementation/pat-io-proof-batch/README.md)
passes 63 pure controls but its actual worker also times out before import, leaving
the installed vault empty. Its verified retained state remains distinct from a
complete import, catalog integration or backed control capacity.

The [whole-worker accounting scope](../artifacts/verification/pat-worker-accounting/README.md)
now records separate parent and child CPU usage, with unchanged project code and
storage bounds. It still fails before import and retains an empty installed vault.
Its verified measurement association does not supply the missing complete import,
aggregate quota, reservation or catalog commit integration.

A [native metadata-scan prototype](../artifacts/verification/pat-native-retention-prototype/README.md)
now passes isolated differential and syscall controls with reduced local CPU cost.
It is not integrated. Faster logical-size observation does not enforce a disk quota
or reserve capacity; those storage obligations remain unchanged.

A hub that runs the agent also stores observations, images, qualification results
and learned PATs. Those workloads must have bounded storage separate from the
capacity owed to ongoing device and driver operations. An accepted motor movement,
PWM burst or driver transition still needs its completion, cancellation and
recovery records when evidence ingestion runs out of room.

The proposed profile separates two durable stores:

| Store | Contents | Behavior when unavailable |
|---|---|---|
| Control authority | Operation identities, ownership, configuration, recovery state, import intents and published references | Refuse work that cannot be recorded; retain unknown outcomes and use the independently qualified local stop/fallback path |
| Bulk evidence | Exact observation/qualification bodies, references and sealed manifests | Refuse new evidence-dependent PAT selection or promotion; preserve access to already admitted control work through explicit control-only recovery |

The design uses separate connections and publishes an authority reference only
after the complete evidence manifest is durably sealed. A crash between those
steps leaves retained, unpublished evidence associated with the original intent.
Reconciliation finishes that same import; it does not launch another worker.
Current-body verification and original-run identity remain mandatory. Missing or
corrupt evidence is unavailable evidence, not a new situation for the agent to
silently relearn or retry.

Each store needs an enforced allocation ceiling, and all writers need aggregate
block/inode accounting that includes journals, temporary files and artifacts.
Admission additionally needs backed capacity for the bounded remaining writes of
accepted work. A quota caps usage; it does not by itself reserve physical space.
Limits must be checked before startup/recovery mutations and after reopening.
The [detailed design](../artifacts/verification/pat-storage-capacity/DESIGN.md)
defines publication states, the proposed evidence snapshot contract and acceptance
work. It is not an implemented deployment guarantee.

The current passing simulated catalog database is 16,199,680 bytes. A read-only
audit attributes 15,440,896 bytes to compact evidence and 758,784 bytes to other
authority btrees. Its remaining 577,536 bytes below the file ceiling are not
reserved capacity. Five small host experiments demonstrate why page caps,
freelist observations and journal retention limits are insufficient on their own.
All original runtime state remains unchanged.

This storage requirement is part of [unified I/O, driver and hub control](io-driver-hub-control.md)
and the [prompt-to-PAT path](prompt-to-pat.md). It does not replace endpoint
watchdogs, bounded local controllers, qualified OS providers or physical testing.
