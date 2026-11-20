# Compiler identity and trusted setup rechecks

This isolated increment closes the two known omissions from the compiler's
selected validation closure: `typing_extensions` and `idna`. It starts from the
[sealed lifecycle candidate](../pat-io-lifecycle-semantics/implementation02/README.md).
The compiler manifest and digest domain move to version 0.2. All seven selected
packages are required for this supported setup; absence is an identity refusal.
Historical version 0.1 evidence remains historical and is not rewritten.

Identity acquisition retains source hashes, package versions and canonical code
closure hashes, including extensionless JSON Schema resources. It bounds selected
files to 8,192, individual files to 16 MiB, and total selected bytes to 256 MiB.
Each distribution inventory also has an 8,192-entry cap before sorting. It refuses
duplicate or escaping selected paths, cache paths, nonregular selected files,
missing files, and an observed size change during a bounded read. These are setup
limits, separate from the unchanged trial/group limits.

`verify_compiler_identity()` re-reads that closure and refuses any mismatch with
the imported manifest. It returns a detached manifest on success and never
refreshes the imported identity. The existing simulation worker's setup identity
now calls it, so changes to selected dependencies cannot hide behind the cached
manifest. Pure compilation and its manifest/digest accessors remain free of
identity acquisition and clock reads.

The selected closure does not itself authenticate actual import origins or the
OS, standard library, dynamic libraries, filesystem path ancestry, Python object
monkeypatches, or future optional validator packages. The reviewed isolated
harness separately pins seven installed distribution inventories and checks actual
origins. A general service still requires the fixed deployment closure, trusted
configuration, process ownership and group evidence association specified in the
[qualification design](../../verification/io-pat-qualification-design/DESIGN.md).
No existing historical fixture attests the changed current candidate.

The exact pure selection contains the 20 existing compiler methods, 14 fixed-unit
methods, 31 I/O contract methods, and 18 new identity methods. The existing
compiler method that executes local runtimes is excluded from this pure run.
The new tests cover the two actual dependency code paths, versions, missing
packages/files, ordering, duplicates, unsafe paths, file kinds, bounded reads,
acquisition ceilings, detached rechecks, worker rechecks and pure lowering.

The explicit project closure excludes the 7,542 historical transcript fixture
files because none are inputs to this selection; all original archives remain.
It retains 213 original project files, changes three of them, and adds one test
module. No live runtime, driver, physical I/O, MCU, inference or service execution
is part of this increment. Primary-agent review is used because the existing
helper agents remain unavailable under their reported account usage limit.

Full current-candidate group execution and aggregate quotas remain unfinished.
This change does not qualify a PAT or mount public qualification tools.
