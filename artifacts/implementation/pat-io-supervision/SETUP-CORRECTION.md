# Create each fixture ancestor privately

The first process test fails before a ledger connection or worker launch with
`UNSAFE_STATE_ANCESTOR`. Its helper used `mkdir(parents=True, mode=0700)`, which
applied that mode only to the final directory. The newly created intermediate
test-method directory had0755permissions and the unchanged state-path guard
correctly refused it. No SQLite connection, supervisor admission or I/O effect
occurred in this attempt. Original directories remain unchanged.

Source03 corrects only the fixture helper to create the intermediate directory
explicitly as0700, then create the final directory explicitly as0700. It does not
chmod the failed fixture or relax the runtime guard. All production source and
236of237project files match source02. Fresh160pure and process1 harnesses keep
their exact methods, limits and audit scopes. The failed process acquisition
allows zero through two parent ledger opens when a test failed; a passing run
still requires exactly two. The original stricter acquisition helper is retained.
