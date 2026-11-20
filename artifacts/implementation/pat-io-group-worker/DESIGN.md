# One current-candidate matrix with a shared capture budget

This candidate starts from the [identity83 source](../pat-compiler-identity/implementation01/README.md).
It connects all 25 named fixed challenges and the candidate domain cases in one
ordered attempt, using the existing matrix 0.3 without dropping cases or raising
its ceilings. A constant GPIO or PWM candidate has 30 cases and reserves 44 child
admissions and 1,676 scheduler ticks. The ordinary parameterized example still
refuses before execution because its combined matrix has 37 cases.

The coordinator reconstructs the current matrix from trusted candidate,
installation and binding inputs. It rechecks the selected compiler/package
identity and the installed source/Python/SQLite closure. It creates one fresh
private runtime per positive/fixed case. Typed negative candidate cases call the
pure compiler with unused fixture keys and create no runtime or authority state.
The positive candidate also exercises exact parent replay and one changed request
under the same original keys. Existing fixed schedules, probes and fault points
are preserved. No replacement-key retry, caller-selected fault or resumed group
exists.

One ledger spans all cases. An ordered ticket binds one declared program to one
engine, charges serialized evidence before writing, includes configuration and
manifest documents, and checks the original deadline at all existing engine
budget boundaries. Scheduler ticks are charged before calls. Every runtime
admission guard checks the case's reserved operation ceiling, including the
original auxiliary probes. A ticket cannot start a second engine or remain usable
after its case ends. The coordinator checks each finished transcript's byte and
record counts against the ticket and checks reported operation/tick counts.
Reused table pages incur no additional charge because no new file is written.

The ledger reserves one maximum-sized terminal document before any work. It can
therefore retain a bounded failure receipt after record exhaustion or deadline
expiry. Failed writes are never refunded or retried. The first exception stops
the group; original raw state and partial records remain. Final success requires
all exact case IDs and a second implementation identity check. Here success is
only `captured`, with all qualification, independent-outcome and attestation flags
false.

Closed SQLite state bytes are observed and included in the 20 MiB derived-closure
check before proceeding to another case. That is an after-close observation,
not a quota on SQLite/WAL growth. Serialized evidence is bounded before writes;
the complete filesystem still needs an actual aggregate quota in the supervised
service. Deadline checks are cooperative; blocking filesystem/SQLite calls need
the separately supervised worker deadline. No claim of hard real-time or OS
isolation is made. The reserved terminal-document bytes are conservative rather
than the exact final JSON length.

Tests select nine ledger boundary cases, two pre-runtime refusals, one complete
GPIO group, one complete PWM group and one reduced-record partial attempt. Each
real group has a separate retained harness invocation so each can be acquired
within the unchanged 16 MiB scratch ceiling. Full-group tests expect all 30 cases,
rehash every record/configuration/manifest, and independently sum serialized
charges, state bytes and reported operation/tick counts. These accounting tests
do not replace the independent semantic outcome composition. If a full group
exceeds a bound, retain that failure and diagnose it; no ceiling is widened.

The next required work joins every current group's independent semantic result,
exact trusted authority/fault setup, current configuration and artifact/run
association. Enforced aggregate storage, persistent supervision and public PAT
qualification remain required. Physical I/O, driver/hub lifecycle providers,
persistent Arduino applications and agent learning remain part of the full goal.

The [actual results](results/README.md) retain a coordinator mapping failure,
its correction, twelve passing pure/preflight methods, a passing real cutoff,
and a full GPIO attempt that reaches 12 of 30 cases before the unchanged 60-second
deadline. The repeated cutoff profile identifies validation reuse as the next
performance investigation. No full GPIO/PWM group has passed.
