# Native retention binding

The original in-process CPython extension passes **43 production-build controls**
and **20 additional controls on a separately instrumented build**. Three actual
production syscall scopes pass: ordinary traversal, FIFO refusal and an audit
veto before any native I/O. [Audited results](RESULTS.json) pin the source,
binary, inputs and trace boundaries.

The [binding](scanmodule.c) releases the GIL around filesystem calls, checks
Python signals, preserves exceptions through cleanup and closes owned directory
descriptors. Controls include thirty real descriptor-exhaustion failures,
one hundred injected child-stream failures, raising/nonraising signal handlers
observed while a scan directory is open, and a concurrent Python observer.
The separate [test shim](faultmodule.c) injects stat/open/stream/enumeration/cleanup
failures and precisely orders fixture replacement and disappearance. It never
forms part of the production DSO. The [raw control results](attempt01/result.json)
retain both processes and their individual receipts.

Opened directories receive additional owner/mode checks, and opened children
must match their pre-open device/inode. The controls demonstrate the original
Python root-mode gap and rejection of an actual substituted directory. This
strengthens the former policy; it does not make traversal an atomic snapshot.

The strict private ABI and failure differences are explicit in the
[design](DESIGN.md). Python audit hooks receive one pre-open native-scan event.
The [observed syscall phases](trace01/collection.json) contain directory opens,
metadata/enumeration, descriptor operations and memory allocation; they contain
no regular-file data reads. Every acquired directory closes. Interpreter and
extension-loader reads occur before the marked scan phase. The veto phase has
no syscalls between its markers.

The [build receipt](build01/receipt.json) records the compiler executable,
Python executable, platform and both DSO hashes. Full compiler/header/linker/libc
closure is not attested. The evaluation loader uses an explicit verified artifact
path and assumes no concurrent modification of that build directory. It is not
a production packaging or sandbox solution. The [API reading notes](research/README.md)
record exact partial coverage of retained official sources.

This is isolated host-runtime work. No original worker state, production module,
public command, Arduino firmware, driver or hub provider changes. There is no
new performance claim or whole-worker result. The [next integration step](NEXT.md)
preserves the complete worker matrix, original deadlines, quotas and failed state.
Review and audit were performed by the primary agent; no independent reviewer
was available for this stage.
