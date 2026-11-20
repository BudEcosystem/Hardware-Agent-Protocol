# Durable supervisor authority and I/O run handoff

The preceding [candidate](../pat-io-document-validation/README.md) has 292/298 passing methods, including the complete reserved-worker scenario, and six retained process failures. It still permits the same reserved request to be sent to a newly created supervisor store. Code identity does not identify that store. This stage implements the missing durable handoff in an isolated candidate; it does not repair prior failures or mount a public service.

## Store identity and compatibility

An explicit version-2 supervisor ledger persists a fresh `supervisor:<32 hex>` authority identity. Creation generates it internally; reopening requires the expected identity. The complete table/index schema and bounded metadata are checked. Missing, partial, unexpected or mismatched state refuses; creation is not migration or repair. The version-1 ledger keeps its existing behavior, and its reader rejects the version-2 metadata. The new supervisor uses the original process/lease/recovery implementation but refuses its legacy unbound `execute` entry point.

The Journal owns a separate immutable execution-mount record, with its actual authority, deployment and the actual bound supervisor identity. Trusted local installation supplies the supervisor object; an operation caller cannot substitute a path, code hash, callback or claimed identity. This initial qualification-service profile has one pinned supervisor per run store and shares its existing single-flight behavior. That is a profile limit, not a limit on the HMS resource graph or future provider bindings.

## Admission and interruption

Execution serializes on the supervisor's existing nonblocking execution lock. No supervisor transaction spans a Journal transaction. Journal transactions may read the ledger, but a ledger transaction never calls the Journal. Calls made from an existing Journal transaction refuse; current authorization is checked within the Journal's transaction. The mount, all retained reservations and all handoff rows are validated before use.

1. Read the original reservation and immutable mount under current administrative authority. If a handoff already exists, locate its exact original request/attempt in the pinned store and return it. A missing or different row refuses; it never authorizes admission. Replay does not plan against a newer configuration or session.
2. If no handoff exists but the supervisor already has the original logical run, reconcile that exact row into the Journal and return it without launch. This closes admission-commit/reply-loss and process-reopen windows. A changed request is a conflict.
3. For a genuinely new supervisor row, verify the reserved inputs against current configuration, actual Registry descriptors, source identities and trusted runtime. Admit with the original image charge, capacity and single-flight checks.
4. Commit a Journal receipt joining its reservation digest, supervisor authority, request digest and actual attempt ID. Recheck current administrative authority and admission eligibility before committing. The committed association is the authorization/admission decision for this isolated qualification job. It is not a lease authorizing effects on the source devices.
5. Only the invocation that created the supervisor row and committed its association may call the original launch path. Replay or recovery never resumes an admitted row silently. Launch failure, lost reply and later worker failures preserve the original row and association.

| Interruption | Required behavior |
|---|---|
| Before supervisor admission | No attempt or handoff was committed; a fresh authorized admission remains possible |
| After admission, before association | Find and associate the original row; do not launch it on replay |
| After association, before launch | Return the original admitted/interrupted row; no second launch |
| After possible launch | Reconcile the original record and actual writer lease; no stored-PID signals |
| Missing row after association or replaced store | Refuse execution while retaining the association and uncertainty |
| Configuration/session/source drift after association | Authorized historical lookup remains possible; it does not authorize new work |

This is not a distributed atomic transaction. A retained record in either store prevents an automatic second attempt after loss of the other association. Coordinated rollback or loss of both stores is outside the guarantee. Filesystem ownership, trusted local installation and the original SQLite durability assumptions remain required. Unknown physical outcomes are not repaired by either database.

## Evidence and bounds

The mount shares the existing Journal connection, transaction and owner. Its exact schema has two tables and one autoindex; it rejects shadow tables, unexpected indexes/triggers, oversize values and broken receipt chains before trusting them. At most 32 handoffs are retained, also bounded by the run store's lower capacity, with fixed encoded-data accounting. No pruning, implicit reset or capacity-widening option exists. These checks are not a filesystem quota.

Controls must exercise legacy/new-profile separation, explicit create/reopen, mismatched/replaced identity, durable request/attempt joins, interruption on both sides of each commit, historical replay after drift, current authorization, concurrent callers, lock order, retained corruption and missing attempts. Tests that stop before launch must explicitly claim only admission/handoff behavior. Real process tests must use the unchanged worker command, complete 30-case matrix and original 60-second limits, retaining any failure. The new source must remain separate until its evidence is reviewed.

The existing deadline and retention-scan failures, aggregate filesystem enforcement, protected control capacity, serialized I/O evidence import, configuration-aware promotion, public tools, learning, persistent Arduino applications and physical device/driver/hub bindings remain open. The full HMS goal remains active. No physical endpoint, acquired controller code, MCU/emulator, live inference/service or adjacent Harness checkout is authorized by this stage. Primary-agent review only while helper capacity is unavailable.
