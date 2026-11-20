# Match the runner's pathname ordering

The completed GPIO process test passes. Its first acquisition stops before
copying the attempt because the helper sorts `Path` objects by their components,
while the runner sorts complete relative pathname strings. The private code
image introduces package and metadata siblings where those orders differ, such
as `attrs/` and `attrs-25.4.0.dist-info/`.

All4,269path/size/hash records match between original raw scratch, the runner's
retained copy and its recorded index. No producer byte changed. The
[failed acquisition](results/attempt05-passed-gpio/failure.json) remains recorded;
the two subsequent state/storage audit commands stopped on the missing proof
before opening any database. The [corrected acquisition helper](acquire-canonical-order.py)
sorts its rows by their relative pathname strings, preserving every bound and
hash comparison. It acquires the same completed run into
[a fresh destination](results/attempt06-acquired-gpio/README.md). No worker was
restarted and no runtime/state limit or mutation key changed.
