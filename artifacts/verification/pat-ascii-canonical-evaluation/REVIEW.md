# ASCII-field canonical encoder evaluation

The preceding namespace conversion is verified progress, with a retained actual
qualification deadline failure. This diagnostic changes no public runtime,
qualification worker, case matrix, deadline, storage limit or authority record.

Compare the exact current guarded canonical encoder with a candidate that
detaches integer-only containers without sorting their ASCII field names in
Python. The guarded C JSON encoder sorts those names. For ASCII strings, Unicode
code-point order and UTF-16 code-unit order are identical. String values may
contain any supported Unicode scalar. A non-ASCII field name anywhere in the
tree selects the complete existing UTF-16-ordering path. Any float selects the
original vendored encoder for the complete value. Neither path passes caller
containers directly to the C encoder. No cross-call value or identity cache is
introduced.

The seven parser/validator/canonicalizer AST definitions and the existing guards
remain exact. Only the byte-generation helper changes, with two new private
definitions. Error wrapping, refusal order, exact types, numeric policy, depth,
node and byte limits remain. This is not a concurrent caller-mutation contract or
complete Python-process attestation; the original scope and limitations apply.

The comparison retains the earlier 1,668 cases and adds 200 fixed generated
ASCII-field trees, one all-ASCII key-order case and six observed route cases:
1,875 differential cases in total. Normal cases also compare with the separate
vendored encoder. Dependency-replacement cases compare current and candidate
fallback behavior. Coverage includes every Unicode scalar as a value/key,
custom hooks (including `isascii`), invalid values and limits, aliased inputs,
UTF-16 ordering, 600 fixed bit-generated floats, six retained upstream vector
pairs and eight retained worker documents. The documents are data; no worker
case database is read or recovered.

Nine fixed alternating timing pairs execute 256 canonical calls each on those
same eight documents, with all guards and validation enabled. The reference for
timing is the currently installed guarded encoder, not the older pure Python
vendor implementation. The number of pairs is fixed before execution; a weak
result is not retried until it looks favorable. These observations cannot prove
whole-worker speedup or qualify a deployment deadline.

One owned isolated child has the original 30 CPU-second, 60 wall-second,
512 MiB address-space, 16 MiB file-size and 64-descriptor bounds. The parent
retains at most 4 MiB output. A cooperative audit hook prohibits child file
mutation, SQLite, network and subprocesses. No HMS package, physical endpoint,
MCU, model, live service or acquired controller executes. Reviewed vendored
encoding code and standard-library JSON are the only non-original algorithmic
dependencies. The hook is not an OS sandbox. Source review is by the primary
agent; no independent review is claimed.
