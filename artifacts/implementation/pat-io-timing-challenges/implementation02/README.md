# Corrected timing refusal composition

The first [candidate](../implementation01/README.md) captured valid no-handoff
expiry behavior, but configuration/refusal composition assumed permission loss.
This source changes only those two independent readers and adds four rehashed
expiry attacks to the new test file. All 7,067 other inherited files remain
unchanged. No runtime/provider/compiler behavior or effect bound changes.
See [review](source-review.json). Full group qualification remains unfinished.
