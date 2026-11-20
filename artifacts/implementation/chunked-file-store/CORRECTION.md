# Correction before attempt02

Attempt01 built successfully and reached the first scope's cold reopen, then
failed with UNKNOWN_ROOT_OBJECT. The runner stopped without starting the other
five scopes. No timeout occurred. All original processes are terminal and absent.
Its 16 MiB image, frozen inputs and raw logs remain exact in
[the preservation inventory](attempt01-preservation.json).

The public header explicitly defines lfs_info.size only for regular files.
lfs_dir_getinfo does not set it for directories. The original hm_stat bridge
read that undefined field and Python inventory compared it to zero. Correct
hm_stat by zero-initializing the structure and selecting size only for REG.
Directories receive an explicit bridge-defined zero; their type and name remain
validated. No upstream source or adapter metadata contract changes.

The six control scopes and chunk_store.py stay byte-identical. The runner adds
an explicit attempt selector and freezes this correction in attempt02. Bounds,
checks and matrix order stay unchanged. This is a source correction followed by
a fresh retained attempt, not an unchanged retry or repair of failed backing.
Both attempts together use at most 112 MiB backing if all second-attempt scopes
start, below the original 256 MiB retained-inventory ceiling.
