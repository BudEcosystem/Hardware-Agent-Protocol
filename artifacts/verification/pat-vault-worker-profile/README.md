# Current worker diagnostic

Status: audited diagnostic; the original integration scope **failed**. Production
is unchanged and the full HMS goal remains active.

The source adds only the previously reviewed bounded profiler around
`run_io_group`. The unchanged compact-catalog process test requests all 30 cases
under its original 60-second worker deadline and 180-second parent bound. It
stopped at the worker deadline with ten case directories, nine manifests and no
complete return. Import, catalog evaluation and source PAT execution were not
reached. The interrupted worker's effects remain unknown.

The profile records 55.648343 seconds of wall time and 27.568436 seconds of process
CPU time over 921 functions. These are observations of an instrumented, interrupted
run, not qualified execution times or an explanation of the earlier uninstrumented
timeout. Cumulative times overlap and must not be added.

| Observed function | Calls | Cumulative seconds | Self seconds |
|---|---:|---:|---:|
| `canonical` | 7,862 | 25.817931 | 0.064424 |
| `check_tree` | 9,087 | 9.584620 | 6.304995 |
| `binding_proof` | 238 | 6.451068 | 0.029226 |
| `parse_topology` | 501 | 4.999453 | 0.080332 |
| fresh implementation digest | 59 | 5.553533 | 0.114416 |

The read-only [audit](audit.py) verifies the frozen source/harness, 286 project
inputs, 159 external inputs, actual imported origins and all 1,033 retained scratch
files (8,078,234 bytes). It reacquires 15 original owner/writer locks, including
the exact supervisor writer inode, and verifies unchanged bytes for three source
databases. It opens **zero interrupted worker case databases**. Source authority
has one original handoff/reservation, no imported runs, operations or claims; its
board counters remain zero. This does not settle interrupted per-case effects.

[Results](RESULTS.json), [source review](implementation01/source-review.json),
[scope](harness01/SCOPE.md), [original failed receipt](harness01/attempts/attempt01-profile/result.json),
[retained profile](harness01/attempts/attempt01-profile/scratch/test_actual_original_matrix_catalog_execution_and_historical_replay/supervisor/9e042290734e4d9c8c96e1a6a0724436/worker-profile.json),
[next work](NEXT.md). Primary-agent review only; no physical device, MCU, model,
live service or acquired controller was executed. The diagnostic signal handler
must never enter production.
