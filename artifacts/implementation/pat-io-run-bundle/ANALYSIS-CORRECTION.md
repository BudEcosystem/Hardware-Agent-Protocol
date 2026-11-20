# Correct the post-test identity-delta assumption

The current source03 run passes all149 tests and its complete acquisition passes.
The first reporting reducer then fails an assertion: it expected only the worker
identity, header and association record to change between source02 and source03.
That assumption omitted the existing synthetic driver's conservative identity,
which explicitly includes all top-level HMS Python modules, including this new
bundle module. The [failed reducer](extend-results.py) and [failure record](analysis-failure.json)
are retained. It produced only an exact copy of the prior source02 analysis
before failing; it did not change test inputs, attempts or production code.

The [corrected reducer](extend-results-corrected.py) verifies the actual closure:
driver and worker digests change, propagating through installation, descriptors,
bindings, static contracts and enclosing hashes. Across37changed example files,
every changed leaf is an exact hash string; all non-hash fields and the complete
matrix case/program bodies remain identical. Candidate, original authority and
logical context documents are byte-identical. The [delta report](SOURCE03-IDENTITY-DELTA.json)
retains every changed leaf's path and both values. This corrects a reporting
assumption and does not waive a test or fresh-verification condition.
