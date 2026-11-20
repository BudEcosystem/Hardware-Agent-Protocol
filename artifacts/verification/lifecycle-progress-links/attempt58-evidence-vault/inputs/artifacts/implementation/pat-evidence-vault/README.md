# Independent evidence-vault component

The candidate stores immutable evidence outside the control journal, with an
exclusive owner, exact expected store identity, enforced per-connection page cap,
atomic complete manifests and checked read transactions. Four production modules
are added; all **275 inherited project files remain unchanged**. See the
[design](DESIGN.md) and [current source](implementation02/project/evidence_vault/store.py).

All **22 distinct methods have passing receipts on identical production code**:
20 controls and the complete retained-data method pass in the first executed
22-method selection; the corrected remaining control passes separately in fresh
state. The [audit](RESULTS.json) preserves the exact distinction between passing
methods and failed scopes. The original full selection remains failed.

| Retained scope | Result |
|---|---|
| [Harness 01](harness01/attempts/attempt01/result.json) | Startup failure: staged supervisor import path omitted; zero methods and SQLite operations, zero scratch bytes |
| [Harness 02](harness02/attempts/attempt01/result.json) | 21 methods pass, one test assertion fails; all source/dependency origins match |
| [Harness 03](harness03/attempts/attempt01/result.json) | The corrected control method passes; production and all resource limits are unchanged |

The failed assertion incorrectly assumed completion releases resource claims.
The correction verifies the claim remains held, records separate synthetic
`resources_quiescent` evidence, then verifies release and original-key replay.
The failed fixture still has its original held claim and remains untouched.

The full retained-data method preserves **4,011 references and 2,798 exact bodies**
from the earlier complete 30-case catalog scope. Its independent vault is
**15,439,872 bytes**, below the unchanged **15 MiB** vault cap by **288,768 bytes**.
All bytes, references, closure, manifest identity, reopen and exact replay are
verified. An independent read-only audit checks five databases under four owner
locks, recomputes the vault implementation/manifest identities, verifies both
control histories and confirms database hashes remain unchanged.

This is storage-component evidence. The vault's authority identifier is explicitly
a fixture, and a supplied binding digest is not authenticated original-run
authority. No new worker ran, and the imported bytes were not requalified by this
component. Authority-owned installation, durable import intents, semantic checking,
atomic reference publication and catalog integration are [next work](NEXT.md).
Aggregate filesystem quota and backed control capacity remain unimplemented.

Read leases invalidate on expiry/release; they do not forcibly interrupt Python
or guarantee scheduling. The vault refuses retained sidefiles and needs a future
qualified hot-journal recovery path. The [primary-source follow-up](../../../research/host-contract/vault-followup/README.md)
records SQLite's locking, journal-pairing and filesystem constraints. Public
mounting, physical providers, prompt learning and the full HMS goal remain open.
