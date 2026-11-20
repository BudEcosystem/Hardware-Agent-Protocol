# Private standing compilation candidate

Source-only and unexecuted. The only changed production file is
`project/hms/standing_pat.py`; [production.patch](production.patch) is its exact
baseline delta. Public compiler entry points retain their parse sequence and
shared predicates. The catalog's private compilation creates one fresh detached
installation snapshot and reuses it only until that pure call returns.

The intended count change is five installation validations to one in private
compilation, and seven to three in complete selection. Policy freshness,
inventory/evaluation/decision reads, evidence/image owners and final commit
checks remain. No persistent cache, authority token, uncertain retry, storage
schema or capacity limit is introduced.

[PLAN.md](PLAN.md) defines two bounded initial profiles: pure equivalence and
nine actual native management/freshness cases. [CONTROL-NOTES.md](CONTROL-NOTES.md)
records their exact scope. Source preparation is not validation: no candidate,
oracle import, compiler, auditor or control has executed. The full original
128-record capacity gate remains required and has no runnable profile here yet.
The original timeout remains failed; limits will not be enlarged to relabel it.

The candidate's host implementation identity must use its actual new source
bytes. The original native image and absolute C qualifier bundle are reused
without rerun or reassociation. Their original12/638 result is C-domain evidence,
not qualification of this host change. No physical/public eligibility or
protected capacity is claimed.
