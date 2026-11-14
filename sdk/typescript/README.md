# @bhms/sdk (TypeScript)

Client, device server and conformance device for the Bhms protocol; behaviour matches the Python reference in `sdk/python`.

## Conformance

Build, then run the Python runner against this SDK's conformance device through its public `--device-command` option:

    npm run build
    bhms conformance conformance-device --device-command "node dist/src/testing/conformanceDevice.js"
    bhms conformance conformance-device:principals --device-command "node dist/src/testing/conformanceDevice.js"

(`scripts/conformance.py` is a wrapper that adds the option for you.) The device accepts
`[URL] [--state-dir DIR] [--memory] [--gateway] [--principals POLICY.json]`.

## State directory lock

One server owns a state directory. On Linux the journal lock is a kernel `flock(2)` held by a `flock(1)` helper process
(util-linux or busybox; no `-E` is needed), so a stdio server opens no listening socket (BHMS-SEC-003). A held lock is retried for up
to two seconds (a restart can race the previous holder's teardown) before the server reports "in use".

If `flock(1)` is missing or refuses its arguments, the server prints a warning on stderr and locks with a listening socket instead
(also what macOS, other Unix and Windows use). **With that fallback a stdio server does hold a listening socket, so BHMS-SEC-003
does not hold**; install util-linux or busybox `flock` to restore it. The two lock kinds do not exclude each other: never run a
flock-locking server and a socket-locking server (for example an older SDK build) on the same state directory.
