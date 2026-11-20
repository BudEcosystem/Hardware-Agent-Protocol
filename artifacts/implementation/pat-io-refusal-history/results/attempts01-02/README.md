# Passing regression and timed-out refusal selection

The 72-method operation/procedure regression passed in 147.279 test seconds
(166.985 seconds including harness work). The combined 56-method observation and
refusal selection crossed its original 180-second execution deadline and was
terminated. It is **not a complete passing result**. Its log contains 37 `ok`
completions, followed by an incomplete method; terminal method counts, origin
receipts and final compiler/driver identities are absent. The outer harness
finished in 190.991 seconds after termination and retention.

[Proof](proof.json) records both terminal states. Both complete attempt trees
and the original empty private scratch roots are retained. Source inventories
before/after match: 7,060 project files, 7,065 frozen preparation files, six
active harness files and 159 selected external files per attempt. The successful
72-method child has 667 checked origins, 197 refused bytecode reads, no recorded
prohibited attempts, and matching compiler/driver receipts. These child receipt
claims cannot be made for the timed-out invocation.

[Original selection](selection-plan.json) remains unchanged. The subsequent
27- and 29-method invocations use the same frozen implementation and original
180-second deadline separately; their outcomes are retained separately. The
failed 56-method invocation remains part of the evidence.

The original `acquire.py` was prepared but never executed. After the timeout,
[terminal acquisition](acquire-terminal.py) preserved the actual states and
rechecked all 4,235 inherited fixture files against their original captures.
No project code was imported during retention. Primary-agent review only;
no complete 128-method pass is established by this result. Physical measurement,
full outcome validation, source attestation and qualification remain unclaimed.
