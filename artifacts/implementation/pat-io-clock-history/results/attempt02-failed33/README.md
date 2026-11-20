# Preserved atomic-release model mismatch

[All33 methods ran](attempt/output.log) in58.077 test seconds and76.037 elapsed
seconds. After the source02 receipt-key repair, both delayed-start positive cases
and the operation unused-context assertion reached the independent authority fold
and failed its claim comparison. The other30 methods passed.

The original journal deletes claims atomically when validated `start_excluded`
evidence excludes any start. There is no later resources-released event in these
captures. The new fold had reset `may_have_acted` but retained its modeled claims.
The [source03 correction](../../start-exclusion-release-correction.patch) derives
that atomic release. Exact receipt evidence still precedes it, and all claim,
fence, operation and parent comparisons remain. Tests and fixtures are unchanged.

The [proof](proof.json) retains the complete8,056-file attempt,727 matched origins,
227 refused bytecode reads and the original empty raw root. No SQLite connection
or device action occurred. Both earlier sources and failures remain retained.
