# Call-local standing compilation reuse

Source proposal only; no implementation, candidate import, test, auditor,
compiler, child or signal has been executed. The sealed history-cost packet was
revalidated at index `559679c886bac679ebac028e3c9d041f3b56f1026e24408a31fe24f45d3b94bd`:
619 files, 13,984,797 bytes. Exact originals and read ranges are retained in
[SOURCE-EVIDENCE.json](SOURCE-EVIDENCE.json).

The measured 32-loop path called `_selected` 64 times. Its 1.928830858 seconds
of exclusive wall time is an aggregate, not attribution to installation parsing.
The whole loop took 8.186641095 seconds, including 2.901843698 seconds outside
the measured method spans. The proposal below removes source-proven duplicate
work; it predicts no duration, speedup or full-capacity success.

## Recommended boundary

Change only the catalog's private compilation path in `standing_pat.py`. Keep
public `installed_artifact`, `parse_artifact`, `compile_artifact` and
`installation_digest` interfaces, validation order and current behavior. Keep
the complete bodies and ordering of `StandingCatalog._fresh`, `_selected`,
`_inventory`, `_evaluation`, `check_selection`, `Policy.fresh`, image/evidence
owners and Journal final commit checks effective.

`_compiled` currently parses the bounded stored artifact and checks its digest,
then invokes the public compiler. Replace that last internal call with a private
compiler that creates one fresh, detached installation snapshot at the original
first installation-validation point. Reuse that snapshot only until this pure
compilation returns. It must not escape through catalog state, `_selection`, a
policy object, producer lease, closure or returned mutable artifact.

Do not reuse the installation approval returned earlier by `_fresh`: the current
`_selected` path subsequently calls held-evidence checks and reads the current
inventory. Retaining that approval through those boundaries would widen the
proof. The proposed private compiler performs its own full `parse_installation`
once after the same artifact-document check that currently precedes it.

There is no caller-controlled `already_validated` option or public token ingress.
A private constructor owns the parsed installation; its construction occurs on
the private compiler's ordinary path, not application ingress. It is not an authority token or a Python
sandbox. Known pure helper calls operate on detached built-in values. No provider,
policy, evidence, database or application callback occurs while it is reused.
It expires by ordinary local scope return/exception, not by a renewed lease.

Factor common pure artifact-construction, typed-domain comparison, endpoint
predicate and compiled-record construction helpers so public and private paths
share one rule set. The public wrappers retain their existing parse calls and
ordering. The private path supplies the fresh local snapshot to those common
helpers, avoiding recursive calls that would parse the same installation again.
Keep installation identity's canonical hashing at each existing result-construction
position; this proposal removes repeated installation validation, not canonical
validation, digest checks or current source attestation.

## Exact successful-path call counts

Let P be `parse_installation`, T be `parse_topology`, G be the private
`_generations`, and B be public `binding_proof`. These are source invocation
counts, not new measurements. The topology schema memo may avoid schema work;
it does not remove the semantic calls counted here.

- One P (`standing_contracts.py:144–212`) calls T directly, `parse_generations`
  which calls T+G, and B twice, each T+G: P=(4T,3G,2B).
- `Policy.fresh` (`256–266`) calls P and an additional B: (1P,5T,4G,3B).
- Catalog `_fresh` (`standing_pat.py:413–423`) retains Policy.fresh plus
  `installation_digest`, which calls P: (2P,9T,7G,5B).
- `installed_artifact` (`91–104`) calls P and installation_digest: 2P.
- `parse_artifact` (`107–123`) calls installed_artifact and another P: 3P.
- Public `compile_artifact` (`144–159`) calls parse_artifact, P and
  installation_digest: (5P,20T,15G,10B).
- `_compiled` (`431–434`) currently calls that compiler. `_selected`
  (`598–627`) calls `_fresh` and `_compiled` once each: (7P,29T,22G,15B).

| Successful operation | Current P/T/G/B | Proposed P/T/G/B |
| --- | --- | --- |
| Public compile_artifact | 5 / 20 / 15 / 10 | unchanged |
| Private catalog compilation | 5 / 20 / 15 / 10 | 1 / 4 / 3 / 2 |
| One complete _selected | 7 / 29 / 22 / 15 | 3 / 13 / 10 / 7 |
| 64 _selected calls in recorded loops | 448 / 1856 / 1408 / 960 | 192 / 832 / 640 / 448 |

There are two `_selected` calls per original reserve: immediate admission check
and its independently registered commit check (`standing_store.py:484–486`).
They must remain separate. Each also retains `_fresh` and every evidence/DB
check. The loop's 32 `hold_selection` entries each add an unchanged catalog
`_fresh` (2P), and 32 ordinary reservations add an unchanged Policy.fresh (1P).
Thus the complete 32-loop source model is 544P currently versus 288P proposed;
the observed 128 Policy.fresh calls remain 128. Setup/final work is excluded.

The three artifact-document decodes in a selected path—inventory, stored row,
then the compiler's artifact copy—remain. So do the four `Compiled.document`
decodes through evaluation/decision/result construction. No reuse spans
`_evaluation` or a current evidence callback. The 2,176 history validations and
their O(n²) progression remain unchanged by this candidate.

## Construction, detachment and refusal order

1. Keep `_compiled`'s `document(bytes(row['document']))` and `artifact_digest`
   check first. A corrupt stored artifact must still fail before installation
   compilation. Keep the additional artifact `document` operation at compiler
   entry. It supplies bounded, detached built-in data with original numeric types.
2. At the old `installed_artifact`'s first P call, perform one complete P and
   own its detached result. P returns its original detached document, not the
   separately normalized topology used during graph validation. Do not substitute
   a normalized graph into identity bytes or reorder hardware resources.
3. Construct the expected artifact with the same `document({...})` operation.
   This detaches CONFIGURATION/LIMITS and preserves exact type checking. Reuse
   the local installation snapshot for its scalar route, instance and digests.
   Compute its installation identity with the original identity domain and
   canonical helper, without another P.
4. Preserve exact artifact fields, identifier checks/allowed label replacement,
   recursive `_same_typed` checks, then the literal endpoint qualification
   predicate. Do not move endpoint qualification before artifact-domain refusal.
5. Construct the compiler identity and fresh Configuration as today; retain the
   same typed Configuration predicate and 32-byte payload. Construct identical
   compilation fields and canonical bytes from the local installation snapshot.
   `Compiled` still stores immutable bytes and a frozen scalar Configuration;
   `.document` still returns a freshly parsed object on each access.
6. `_compiled` still returns its first detached artifact, independent of the
   compiler's separate artifact copy. Expected-artifact label edits never mutate
   caller/stored objects. No topology, generation dict, CONFIGURATION or LIMITS
   object is newly shared into a returned mutable record.

Public entry points retain behavior for arbitrary caller input, including the
existing `document` deepcopy path; they do not receive this private shortcut.
Simultaneously malformed artifact+installation inputs must retain the public
artifact-document-first refusal and subsequent precedence. The private path's
catalog inputs come from stored bounded bytes and `_fresh`, and it still fully
validates its own installation snapshot before reuse. No supported callback may
be added inside that pure segment; if implementation reveals one, split the
segment or abandon the shortcut instead of retaining approval through it.

`_compiled` also serves `record_evaluation`, `promote` and `_evidence_guard`, not
just selection. Their calls are therefore affected and require controls. Every
guard invocation constructs a new snapshot: neither the current-vs-expected
compilation check nor held receipt/source/binary ownership is removed. Public
publication parsing and original run/decision association remain unchanged.

## Planned controls and execution gate

No control source or runner is implemented by this proposal. The next isolated
candidate should retain exact baseline source and an independent old-path oracle,
then submit its complete delta and bounded runner for review before execution.

- Compare candidate private compilation and unchanged public/baseline compilation
  for exact artifact and compiled bytes, all digests and Configuration payload.
  Include allowed labels, legal resource/list orderings and fresh independent
  input/returned objects; mutate caller/returned/expected objects between calls
  and prove no prior approval or mutable alias survives.
- Prove source counts with bounded control-only wrappers: private P=1, public
  P=5, complete selection P=3; each existing policy/current/evidence/commit guard
  still runs. No global parser/encoder monkeypatch is needed for timing claims.
- Compare refusal class/code and precedence for malformed JSON, duplicate keys,
  oversized/deep inputs, bool/integral-float substitutions, missing/extra fields,
  invalid labels and endpoint domain, plus paired malformed artifact+installation.
  Public wrappers retain their current deepcopy behavior and parse order.
- Reject physical-atom/driver-slot mismatch, missing per-alias driver dependency,
  changed generations/source digest, capacities and source epochs. Keep physical
  proof exactly two atoms and shared finite/standing claims exactly three.
- Change source/encoder/validator/constants or installed input between independent
  calls and require the original current checks/refusals. No retained snapshot
  may bypass changed helpers, current source identity or a catalog update.
- Exercise management evaluation/promotion/original-run conflict, current
  artifact/evaluation/decision mutation, multiple promoted labels, policy
  replacement/withdrawal, held-image/evidence expiry and late commit withdrawal.
  A checkpoint after initial selection must still force a fresh final selection;
  rollback, reopen and different owner instances must not reuse any snapshot.
- Reuse the actual original native pipe and absolute qualification bundle for
  meaningful selection/admission/shared-claim and unknown-replay controls. Bind
  candidate host source identity honestly; the old C qualifier receipt is still
  its original C-domain evidence, not a new host optimization qualification.

After semantic controls pass, run the complete original mutation-capacity path,
including 119 never-handed-off keys, ordinary refusal and reserved settlement
continuations, with its original 128-record semantics. Preserve the earlier
failed attempt. Use the already declared capacity profile (30-second wall/CPU,
512MiB control, 5-second CPU/256MiB native, FD64, bounded owned cleanup and its
separate 32MiB file limit); do not relabel a larger limit as the 1MiB diagnostic.
Do not increase any limit or prefill via SQL. Stop and retain any failure.

This proposal does not claim that the full capacity run will fit. It does not
resume the halted existing-state-replacement branch, add a persistent cache,
alter driver/device execution, grant physical/public eligibility or establish
protected storage. The implementation-ready action is the single isolated
private compilation refactor and its equivalence/freshness controls after review.
