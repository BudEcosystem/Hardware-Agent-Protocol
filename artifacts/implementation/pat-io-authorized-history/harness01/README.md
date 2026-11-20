# Isolated authorized-history103 harness

Run 20 composed-history methods, all 48 configuration methods and all 35 board
methods against the frozen candidate. See [scope](SCOPE.md), [targets](targets.json)
and [index](index.json). Original 180-second deadline, 16 MiB scratch retention,
source-only origins, SQLite/network/subprocess prohibitions and owned-child
retention remain unchanged. No Runtime or physical/inference service runs.
Preparation and complete adaptation-diff review precede release; results are
separate. Helper account limits prevent independent review.
