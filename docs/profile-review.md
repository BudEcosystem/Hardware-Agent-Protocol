# Description/profile review disposition

Two independent reviews examined the new description direction and its exploratory checker. These findings concern draft descriptions and static lint, not a demonstrated runtime vulnerability. The current fixtures remain synthetic and uncommissioned.

The WoT specialist identified four issues: `additionalProperties` was outside the TD base context; action inputs lacked units; recipe identifiers admitted fractional values; and the local schema's hash pin was not enforced by the checker. The TD keyword was removed, input units and a draft focus frame added, recipe values restricted to integer enum values, and a digest check added. Strict payload validation remains a separate execution-contract requirement.

A separate consistency reviewer reproduced three further defects through in-memory mutations:

| Finding | Repair | Regression evidence |
|---|---|---|
| `readOnly: true` property could advertise `writeproperty` | Explicit per-affordance operation allowlists in this fixture profile | Mixed read/write form is rejected |
| String input with retained `properties`/`required` passed envelope checks | Require object input, string identity fields and object arguments | Scalar envelope, numeric operation key and scalar arguments are rejected |
| Rebinding the `hms` prefix changed semantic meaning while literal-key checks passed | Pin the exact draft root context for these fixtures | Same prefix with different namespace is rejected |

The consistency reviewer found no further material contradiction among the execution, workflow/material, learned-control and transport documents it inspected. That is a bounded review result, not proof of completeness. The SiLA binding document was completed afterward and was not included in that review. The transport and laboratory binding texts explicitly defer bounded-stop admission to the execution core's commissioned exception.

The reviewed inputs preceded the repairs above; their hashes identify that historical input, not the current files:

| Input | SHA-256 |
|---|---|
| `scripts/check_wot_profile.py` | `54d383bd056795f01e38dae9c232f1c4e55bc96afeec173f7385fb4356edad84` |
| `spec/02-execution.md` | `3fd0ebb60a4a4436269601d5589711524f5c33169827b57f9bbbd4eb2a0f84b1` |
| `spec/05-description-profile.md` | `59900223e4d63cb44479dfab0f6f7d1d1fbf5c5e770146d24be8cf6810daad95` |
| `spec/06-workflows-materials.md` | `4d4a310000288cfb5363428f35309a7398e7ee46c53f40f7793a784a8a4bd251` |
| `docs/learned-control-profile.md` | `bbc70ee3fcf0b1172937d1c09c9cf0c1dd6330fba19cf63256b9970a1e087642` |
| `docs/transport-guarantees.md` | `c30a9d7b5191cc57281dc54ff8ef8ede3ee08403390745dc9bdaa060d86287e1` |

After these repairs, all 21 local unit tests passed. The suite covers exploratory description behavior; runtime negotiation, operation admission, wire interoperability and physical evidence remain unimplemented.
