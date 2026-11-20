# Policy object identity at finite commit

Status: source-only correction; no candidate execution. The exact271-file freeze02
and its source review are preserved under `history/source-freeze02`, verified
before modification. `revision-03.patch` records the delta from that freeze.

Independent source inspection confirmed a reachable installed-hook boundary:
Journal calls `submission_record` after policy admission, and dispatch `_reserve`
after policy recheck. Either trusted hook can replace the mutable
`journal.policy` attribute. The retained final closure previously called the old
policy object's `fresh(context)`, which validated that old object's enabled state,
image and installation. Journal's commit checker protects callback/connection
purity but does not capture policy identity. Thus replacement could leave a
transaction authorized by a policy object no longer attached to the authority.
This is an installed-service reconfiguration boundary, not a caller JSON feature.

`InstalledPolicy.fresh` now requires `self.journal.policy is self`. The finite
final closure additionally captures the admitting Journal and requires that the
policy remains associated with that same object through COMMIT. Both checks are
pure and use the existing commit callback. They do not add a new lock, schema,
provider or authority. Default/public profiles remain unchanged.

A nineteenth original control replaces the policy object in submission's record
hook and dispatch's reserve hook. It expects typed refusal and rollback: no
new operation/claim after failed submission; the original accepted state, no
attempt ID, no possible effect and the retained claims after failed dispatch.
The control restores only its installed test policy for inspection/cleanup and
checks zero native output dispatches. This is proposed source, not passing test
evidence. Actual killed-owner and remaining retention/negative controls stay
outstanding as listed in PLAN.md.
