# Public Runtime read-tool demonstration — source only

`runtime_probe.py` is unexecuted. Root must review the source and its pins before
running `/usr/bin/python3.12 -I -B artifacts/implementation/prompt-intent-handoff/demo/runtime_probe.py`.
The only destination is a new, exclusive `demo/runtime-probe-attempt01`; an
existing destination refuses rather than reopening, replacing or retrying it.

The root-authored, pinned `demo/prompt.txt` requests one simulated home fan
bench check: 37 percent, then zero after completion, proposal only, with no
persistent controller and no command execution. This probe records actual public
Runtime `discover`, `describe`, and two `observe` results. It does not interpret
the prompt, create a proposal, or invoke a model. Root will inspect the replies
and author the external-agent proposal separately; the sibling intent demo
consumes those original replies. The four attached rows have exactly
`method, params, reply, sessionId, callId`; the last two are null. The full
attachment is bounded to 16 KiB. A failed tool/read assertion fails the probe;
no fabricated successful or fallback replies are written.

The probe verifies the pinned historical receipt and all 244 exact public
file hashes and lengths before importing public `hms.runtime.Runtime`, then
again after closing it. It checks the interpreter and its own source and root-authored prompt pins.
It refuses pre-imported `hms`, inserts only the public repository as the new
source root, and uses an exclusive absent bytecode-cache prefix with `-B` to
avoid loading existing unpinned `.pyc` images. Every loaded `hms` module is
joined to those public source pins. The trusted Python/SQLite/jsonschema/OS
runtime closure is not fully pinned or sandboxed; source checks before/after
are not a hostile-same-user path-replacement defense.

The Runtime uses its existing explicit legacy `simulation:local` profile,
bootstrapped to `demo:prompt-reader` only in the new private state directory.
It creates the ordinary SQLite simulator, registry and procedure schema and
initial observations. Creating this state writes local files; the four tool
calls themselves are read methods. No worker starts, scheduler tick, namespace,
prepare, invoke, procedure, PAT evaluation, C qualifier or native child is used.
The default actual host clocks are retained. The 600000 ms observation query
limit records a current read reply; it is not a later invocation's freshness
permission. The captured replies remain simulation evidence, not hardware
truth, qualification or currently valid authority after process close.

A process audit hook refuses Python process-launch and socket audit events.
The one-process source path never starts workers, and before/after checks
require one native/Python thread, an empty kernel child list and zero child
CPU usage. This is a bounded trusted original path, not universal containment
against arbitrary native extensions. The process has 30 s wall/CPU, 512 MiB
address space, 1 MiB per file, 64 descriptors and zero core limits. The wall
timer interrupts the probe; terminal cleanup masks INT/TERM/ALRM/XCPU, closes
Runtime, verifies output/source state and exits without re-enabling deferred
signals. Every output is bounded, with a final 16-file/4 MiB inventory ceiling;
this aggregate check is observed after writing, not reserved disk capacity.
There are no child processes to signal or reap.

Independent query-only SQLite connections inspect all finite operation,
claim, replay, namespace, event and procedure-work tables before and after the
reads. Every such count must remain zero. Plant receipts and fences must remain
empty; all three original simulated devices must retain initial value zero
and effect count zero. The actual closed state and both snapshots are retained
alongside `discovery.json`, `prompt.txt`, public pins and `RESULTS.json`. The
RESULTS output inventory excludes its own root record; all other files are
hashed. A successful probe claims these actual reads and zero-work checks only.

Source mappings inspected for this original probe: `hms/runtime.py` 1–220,
215–270, 330–545; `hms/local_adapter.py` 1–135; `hms/simulator.py` 1–105,
170–195; `hms/installations.py` 1–105; `hms/demo.py` 1–73;
`hms/registry.py` 590–755; `hms/journal.py` 15–60, 120–185;
`hms/procedures.py` 20–52; `hms/state_path.py` 1–71. No whole dependency-graph read is claimed. The manifest supplies exact source identities independently
of these selected source reads.
