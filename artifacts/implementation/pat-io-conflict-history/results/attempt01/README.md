# Failed combined retention;52 methods reported passing

The first invocation ran all 52 selected methods with zero test failures/errors
in128.563 test seconds and 135.348 elapsed seconds. The overall attempt **failed**:
its 2,929 raw files total 16,817,257 bytes, exceeding the original 16,777,216-byte
collection ceiling by 40,041 bytes. That limit was not raised.

The original raw directory remains `/tmp/hms-io-conflict-history-conflict52-u8q8d5by`.
Its bounded [hash inventory](raw-scratch-index.json) is retained; oversized raw
output was not copied into this result. The source, harness, log, terminal
receipts and input inventories were acquired as 7,100 attempt files. This is
not a successful whole-attempt retention result. See [proof](proof.json).

The same frozen source subsequently passed two disjoint selections:
[48 transcript/conflict tests](../attempt02/README.md) and
[four legacy runtime tests](../attempt03/README.md). Each keeps the original
180-second deadline and 16 MiB scratch limit. The failed attempt remains intact.
No PAT qualification, physical control or full fault-matrix result is implied.
