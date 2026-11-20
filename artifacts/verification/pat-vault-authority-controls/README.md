# Current authority-vault controls

Status: **25 distinct current-production methods pass in separate scopes**.
The [independent audit](RESULTS.json) verifies 22 methods in this stage plus the
three prior correction controls on identical production. All 284 inherited
project files remain unchanged; one test module adds five boundary controls.
The [source snapshot](implementation01/README.md) contains 285 project files.

These controls cover authority-owned installation, original import intents,
publication boundaries, lost replies, revocation, configuration/implementation
drift, evidence corruption and unavailability, capacity refusal, schema and
transaction boundaries, and installation rollback/reconciliation. The
[selection](selection.json) names every method. Historical replay is distinct
from eligibility to execute a PAT in the current device/driver/hub context.

The audit opens **45 retained database copies under 60 owner locks**, verifies
exact bodies, closures, original associations and implementation identity for
the selected intact histories, and confirms all database hashes are unchanged.
It also confirms that deliberately corrupt bytes and malformed records remain
unrepaired, and that a failed installation remains uninstalled. It imports no
production modules and does not reconstruct original lease identities.

| Selection | Verified scope |
|---|---|
| Mount and cold publication replay | [01](harness01/README.md) |
| Semantic refusal and pre-intent rollback | [02](harness02/README.md) |
| Same-intent and sealed-evidence resume | [12](harness12/README.md) |
| Pre-publication interruption and lost reply | [04](harness04/README.md) |
| Revocation and changed original attempt | [05](harness05/README.md) |
| Corrupt and unavailable evidence | [06](harness06/README.md) |
| Capacity and reads outside the control transaction | [13](harness13/README.md) |
| Schema and transaction reentry | [08](harness08/README.md) |
| Full vault and changed consumer identity | [09](harness09/README.md) |
| Malformed record and installation rollback | [10](harness10/README.md) |
| Lost installation reply and changed-configuration history | [11](harness11/README.md) |
| Prior configuration/revocation correction | [Prior 18](../../implementation/pat-vault-authority/harness18/README.md) |
| Prior snapshot expiration | [Prior 19](../../implementation/pat-vault-authority/harness19/README.md) |

## Retained interruptions and limits

Original scope03 has no final receipts; its recorded processes and temporary
state were absent after continuation. Its surviving files and that observation
are retained in [the interruption record](interruption-observation.json). Scope12
uses fresh state with identical methods and bounds. The original remains unverified.

Original scope07 returned tool exit 143 without final receipts; its recorded
processes were absent. The cause is not established. Its 51 remaining raw files
were copied byte-for-byte without opening any database. The
[observation and inventory](interruption07/observation.json) retain that state;
scope13 passes the same two methods in fresh state. The original remains unverified.

Completed scopes01/02 and prior18/19 retain verified scratch copies, while their
historical temporary directories are now unavailable. Earlier retention receipts
remain unchanged. The new audit records present availability explicitly; it does
not recreate those trees. The failed `python` shell launch before scope04's actual
`python3` launch is retained in [the launch observation](launch-observation.json).

Every executed scope keeps the original 180-second parent deadline, 120-second
child CPU limit, 512 MiB address-space limit, 16 MiB single-file limit, 256 MiB
scratch bound and five-second production snapshot. No aggregate quota or physical
capacity reservation is established. Cooperative audit hooks are not OS isolation.
Method coverage does **not** pass the preceding failed aggregate timing scope.

The controls use a declared substitute semantic oracle. No actual qualification
worker or physical device ran in this stage. An actual original 30-case run through
this importer, catalog integration, public mounting, prompt learning, persistent
MCU applications and real I/O/driver/hub providers remain open. [Next work](NEXT.md)
retains those requirements; the full HMS goal remains active.

The [research continuation](../../../research/host-contract/pragma-completion/README.md)
fully reads the retained PRAGMA page's 2,688 prose lines and three inline diagrams.
The wider research backlog remains incomplete.
