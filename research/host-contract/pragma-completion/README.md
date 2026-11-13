# SQLite PRAGMA reading continuation

The [retained source](../capacity-followup/raw/pragmas.html) is the official
[PRAGMA reference](https://sqlite.org/pragma.html), acquired on 2026-11-08.
This continuation reads all 2,688 LF lines of its
[extracted text](../capacity-followup/text/pragmas.txt). The previous selected
251-line reading and its immutable receipt remain unchanged. No linked page or
downloaded JavaScript was executed or counted as read.

The [reading receipt](reading.json) records exact ranges and source hashes.
All three inline syntax diagrams were read as SVG markup and visually inspected
using local renders. The [visual receipt](visual-review.json) records the exact
images and the retained rendering failures. The site banner is decorative.

## Source notes

Unknown pragmas may be silently ignored, and some act during preparation.
`data_version` does not change for the connection's own commits. Temporary-store
behavior depends on build options. `query_only` is not an operating-system
read-only boundary. Integrity checks have coverage differences; foreign-key
checking is separate. A journal retention limit is not a live aggregate quota.
DELETE-mode EXTRA adds directory synchronization; guarantees still depend on the
storage stack. Trusted-schema policy is per connection. WAL checkpoint modes
differ in waiting behavior. Writable schema can corrupt a database. The syntax
diagrams show an optional schema prefix, optional value supplied by assignment or
parentheses, alternative value forms, and an optional numeric sign.

## HMS implications

Read back required connection settings and pin the actual SQLite build. Do not
replace evidence validation with `data_version` caching. Preserve separate
control/evidence admission budgets and explicit recovery states. A successful
pragma call, integrity check or commit does not prove physical reservation,
bounded latency or device safety. The retained page describes newer features
than the tested local SQLite 3.45.1; applicability requires version checks.

This completes the retained page's prose and three inline diagrams. Linked
references and the wider research backlog remain separate work.
