# Finite capacity control uses legal execution transitions

Status: source-only test correction after root attempt03. Freeze06's exact279
files and source review are preserved under `history/source-freeze06`; attempt03
remains unchanged. Root reported both builds and original12/638 passing, nine
host cases/81 checks passing, ten native cleanEOF exit0 records and four outer
reaps with the owner empty/closed. The failure was a test error: repeated
record_execution(running) calls violate the unchanged public state machine.

The corrected control makes one legal dispatching→running transition. Accepted,
dispatch_claimed and running execution_evidence are the first three ordinary
events. Five bounded trusted `_event` writes in explicit transactions use the
label `control_capacity_fill` with testOnly=true; the existing classifier at
Journal lines504–524 treats this nonreserved kind as ordinary. These writes are
test-only storage filling, not additional execution transitions or a new public
API. The control requires the exact eight original events, refuses the ninth,
and compares retained event rows plus operation status to prove rollback. It
then performs the original public cancel request, cancel acknowledgement,
canceled terminal evidence and resource release, requiring all four retained
continuations and the unchanged first eight records.

No production code, SUCCESSORS transition, capacity classifier, twenty-case
count or cap is changed. The fixed runner exclusively creates host-attempt04,
uses fresh qualification IDs ending in`:4`, and pins all three prior result
hashes before/after commands. `revision-07.patch` captures this delta. The revised
source has not run; outstanding owner-death and remaining qualification gates
are unchanged.
