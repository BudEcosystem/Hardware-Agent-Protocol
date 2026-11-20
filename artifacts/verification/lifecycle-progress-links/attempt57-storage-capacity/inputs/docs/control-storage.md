# Control storage for devices, drivers and the intelligence hub

Status: required design, with bounded SQLite observations, 2026-11-08. The current
runtime does not yet implement protected control capacity or a qualified aggregate
quota provider. [Review and evidence](../artifacts/verification/pat-storage-capacity/README.md).

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
