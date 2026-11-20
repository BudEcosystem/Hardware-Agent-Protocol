# Correct the identity-change test injection

The first run executes all 148 methods: 147 pass and one new method fails at its
second assertion. The first assertion changes the `_source_identity` global used
inside the existing identity function and observes
`PAT_IO_GROUP_IMPLEMENTATION_CHANGED` as expected. The second assertion patches
`hms.pat_io_group_worker._identities` after `pat_io_group_setup` has imported that
function by value. Setup retains its original function reference, so the test
does not actually inject a changed implementation identity and no mismatch is
expected from the production code on that input.

Source02 changes only this test's patch target to
`hms.pat_io_group_setup._identities`, the reference that setup actually calls. It
also requires that mock to be called exactly once. The assertion still requires
`PAT_IO_RUN_BUNDLE_FRESH_MISMATCH` for the changed worker digest. Every production
file and 229 of 230 inherited project files remain byte-identical. No validation
guard or bound is changed. Source01, its failed run, acquired copy and original
raw scratch remain immutable. A fresh run uses the same exact 148-method list.

The raw scratch prefix still contains `snapshot-reuse` inherited from the prior
harness. Exact source/harness pins and acquisition records identify this bundle
stage; the prefix is not used as provenance or authority.
