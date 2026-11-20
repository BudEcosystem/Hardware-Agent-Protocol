# Prepared-statement research and local source observation

Three primary sources are retained and fully read in their declared scope:
**477 LF lines** comprising two complete SQLite API bodies (121 + 151) and the
complete pinned CPython v3.12.3 `statement.c` (205). Raw responses, extraction
metadata and exact hashes are retained. The API bodies include their signatures
and final reference lists; navigation/scripts are excluded. No meaningful body
images were reported. Linked references and the broader Python SQLite library
documentation are not covered by this full-read claim. No acquired code ran.

Prepared statements hold compiled SQL. Their lifecycle separates preparation,
parameter binding, evaluation, reset and finalization. This supports investigating
reused compilation while retaining current data reads; it does not justify
caching observations, permissions, schema facts or evidence. [SQLite statement
object](https://www.sqlite.org/c3ref/stmt.html)

The v2 preparation API retains SQL text for automatic recompilation after schema
changes and, for some query plans, parameter changes. Recompilation has a retry
limit and can fail; reuse does not provide a timing bound. Preparation compiles
one statement and returns the uncompiled tail, and finalization remains the
caller's responsibility. [SQLite preparation](https://www.sqlite.org/c3ref/prepare.html)

The pinned CPython file converts SQL to UTF-8, checks SQLite's SQL-length bound
and embedded NULs, calls `sqlite3_prepare_v2`, and rejects a second statement after
skipping whitespace/comments. Its DML-prefix recognition supports transaction
behavior, not a general authorization boundary. It releases the GIL around
preparation and finalization. This file does not implement the connection cache
or prove callback-replacement behavior; its headers and other implementation
files remain outside this packet. The upstream source tag does not attest this
host's compiled extension. [CPython v3.12.3 statement implementation](https://raw.githubusercontent.com/python/cpython/v3.12.3/Modules/_sqlite/statement.c)

The separate [local observation](OBSERVATION.json) pins current project source,
the executable/SQLite extension and the installed `connect` text signature.
The API reports `cached_statements=128`; both HMS authority and board connection
constructors leave that argument at its default. The exact closed inventories
produce **164 distinct authority SQL statements and 28 board statements** per
complete capture. This is a static capture-only count, excluding startup and
other runtime SQL. It suggests possible cache eviction, but no cache misses or
timeout cause have been measured.

The existing [authorizer review](../authorizer-followup/NOTES.md) remains relevant.
Current Journal and catalog code replace connection authorizers around commit
and evidence checks. Any cache-capacity experiment must preserve those guards,
test refusal of previously prepared writes, verify restoration and schema/data
changes, and measure preparation separately from execution. A larger statement
count also needs bounded memory accounting; it does not provide disk capacity,
backed control continuation space or device quiescence.

The [metadata-query experiment](../../../artifacts/verification/pat-sql-metadata-evaluation/README.md)
preserved 410 cases but failed its performance screen. It remains unadopted.
The next experiment may compare the unchanged full capture SQL at the default
cache size and one declared bounded alternative. It must measure the hypothesis
before any integration and retain the original complete-worker deadline.
