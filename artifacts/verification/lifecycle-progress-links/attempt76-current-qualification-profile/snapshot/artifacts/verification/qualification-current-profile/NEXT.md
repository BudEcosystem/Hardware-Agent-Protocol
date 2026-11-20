# Reduce measured work without weakening capture

The current profile replaces an outdated cost picture. Keep the ASCII encoder
candidate unadopted, all earlier failures intact and the diagnostic wrapper out
of production. The diagnostic does not qualify timing or physical effects.

Evaluate consolidating fresh SQL metadata queries in the two table-capture
functions. They currently acquire schema, row count, storage classes and maximum
cell sizes through separate statements before loading rows. A candidate may
combine bounded scalar metadata in one query while preserving schema checks,
row-count checks, type/size refusal order, per-cell validation, exact page bytes,
complete inventories, lock scope and original budgets. Every capture must still
read current data. Do not introduce a database-state cache, trust timestamps as
source identity, skip malformed-storage checks or remove flush/fsync barriers.

First compare exact original and candidate functions on bounded, independently
constructed SQLite fixtures. Include empty tables, every storage class, row and
cell-size limits, schema drift, public metadata filtering, invalid UTF-8/JSON,
and simultaneous invalid conditions that determine refusal order. Test changes
between metadata acquisition and row loading as well. Retained JSON transcripts
may be used as data; no interrupted worker database may be opened or repaired.
Verify exact bytes/refusals and actual statement counts before considering a new
complete-matrix qualification attempt. Whole-worker success remains separate
from local function measurements.

The broader installation requirements remain: backed control continuation
capacity, hard aggregate block/inode enforcement, caps before startup recovery
and explicit control-only recovery. Finish the installed qualification service,
typed public PAT CLI/MCP methods and native Harness integration, then prompt
synthesis, learning and deterministic reuse. Continue persistent MCU controllers,
physical I/O, driver and intelligence-hub providers, microscope work, remote
authority/streams, full research and home/laboratory/manufacturing validation.
Neither the diagnostic nor an optimization completes those requirements.
