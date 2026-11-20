Targeted read-only delta review of immutable lifecycle draft02. The three
concrete source findings recorded against draft01 are addressed in these bytes:
publication replay derives its exact after-snapshot proof and historical binding,
revision/mapping carriers are checked before use, and the added current-operation
lookup precedes the final inherited clock veto. This is source review, not proof
that the 30 drafted lifecycle tests pass; none were executed or imported.

The reviewer ran only `check_extraction.py`, an original stdlib AST comparison
that reads copied sources without executing project code. It confirms the
original public administrator prefix and shared binding/release bodies remain
unchanged after the explicit transaction guards and the deployment-argument
rename. `extraction-result.json` and its log retain that narrow static result.

The static/live resolver split keeps identity, authorization, typed arguments
and scope checks for future bound steps; live admission and dispatch still check
current revision/token/nonreuse. These are distinct checks, not a grant to run
future parameters early. The coordinator still holds the authority mutex and
board lock across its single authority settlement transaction.

Public lifecycle output is now explicitly tagged with a distinct profile, but
current public API validation intentionally does not accept that profile. The
ordinary reviewed I/O result change has not yet been ported to this draft.
Neither lifecycle mounting nor end-to-end API compatibility is approved here.

Only the targeted changed seams and their surrounding code were reviewed again;
this is not an exhaustive review of every retained file or every failure window.
The complete selected sources are acquired for provenance, not an expanded
full-reading claim. The earlier draft01 unresolved record remains untouched.
