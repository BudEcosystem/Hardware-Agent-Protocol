Exact live provider port, awaiting shared integration freeze

The six provider modules, exact hashed-board state-path allowance, and normal-import provider test were copied byte-for-byte from the sealed current-baseline provider proof. The eight live files and copied snapshots are pinned in `handoff.json`; all538 source-proof records and150 pre-integration records were hash-checked before copying. Only stdlib AST parsing was used. No HMS import, test or Runtime execution occurred during the port.

Root separately owns public Runtime/bootstrap/daemon configuration and its tests. IoRuntime imports Runtime at module scope, so a new reverse dependency must be lazy. The inherited staging docstring is intentionally unchanged here; root must correct it if later mounting changes the statement. Earlier24-test evidence does not establish the new combined integration closure. Wait for shared source freeze before testing.
