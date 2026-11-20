# Reject key subclasses before comparing path sets

Final source review after the passing148 run found a validation-order edge case.
The parser checked the supplied mapping's path set before checking that every key
was an exact builtin string. A caller could supply a string subclass whose hash
or equality method runs while constructing that set, before the parser eventually
rejects the unsupported key. Canonical byte documents do not need such hooks.

Source03 keeps the exact builtin mapping/count check first, validates all key and
value types and byte bounds next, then compares fixed path sets. Its new test
constructs a subclass key before installing raising hash/equality callbacks and
requires a document refusal without invoking them. No wire representation, hash,
setup semantics, authority, runtime or limit changes. Existing148 methods remain;
the new selection contains149. Both earlier source versions and complete attempts
are retained. This is a static-review correction followed by a fresh test run,
not a retrospective claim that the earlier test selection covered this case.
