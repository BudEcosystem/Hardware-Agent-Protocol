# Local IPC source review

The [manifest](manifest.json) records archived source bytes and SHA-256 hashes for selected sections read on 2026-11-06. Coverage is partial: Python 3.12 socket address representation, `getsockopt`, `settimeout` and `sendall`; Linux `unix(7)` pathname permissions, `SO_PEERCRED` and `struct ucred`. This is not a complete Python or kernel security audit.

Python exposes Unix socket paths and returns a byte buffer for structured socket options; timeouts apply to socket operations. The transport therefore decodes peer credentials and recomputes each remaining I/O timeout from a monotonic deadline. [Python socket documentation](https://docs.python.org/3.12/library/socket.html)

Linux pathname sockets respect directory/socket permissions. `SO_PEERCRED` returns credentials associated with the connection, using `struct ucred`. The implementation authenticates the peer UID and treats every process with that UID as the same principal. It does not claim current process identity after descriptor transfer or per-agent isolation. [Linux unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html)

The two-second budget, 64-KiB framing limit, sixteen worker slots, private directory requirement and experimental JSON envelope are local design decisions. Socket deadlines cannot cancel a blocked in-process runtime handler; the runtime's bounded local methods and orderly handler draining remain explicit assumptions.
