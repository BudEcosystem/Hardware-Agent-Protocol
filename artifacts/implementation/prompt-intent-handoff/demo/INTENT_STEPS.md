# Prepared external-agent planning demonstration

Source prepared; these commands were not run by their author. The root agent
reviews and owns any later executions. The public Runtime probe is a separate
process/source handoff from `runtime_probe.py`; this avoids mixing the minimal
retained parser package with the full public Runtime package in one interpreter.

After the real runtime probe returns `prompt.txt` and `discovery.json`, create a
new trace directory and a separate new mutable planning-store directory:

```sh
python3 -B -I artifacts/implementation/prompt-intent-handoff/demo/intent_demo.py prepare \
  --attempt /absolute/new-prepare-attempt \
  --state-dir /absolute/new-live-intent-state \
  --prompt /absolute/runtime-probe-attempt/prompt.txt \
  --discovery /absolute/runtime-probe-attempt/discovery.json \
  --owner external-agent-demo-owner \
  --application application:fan-demo
```

The invoking local host supplies the trusted owner anchor. The command validates
the actual known read-result shapes, retains the exact prompt bytes, stores the
initial intent, and returns an `awaiting_proposal` handoff. It generates no PAT or
language interpretation. Discovery provenance is not authenticated by accepting
this file; use the separate real probe trace for its origin and zero-operation
checks.

The current external agent reads the retained prompt, discovery, description and
observation replies plus `status.json`, then authors a `proposal_put` request file
using the closed field contract. It supplies the returned application/revision/
handoff identity, its own interpretation and candidate or honest unresolved
outcome, and the exact retained discovery array. Attribution kind must be
`external-agent`; unknown Session/model identifiers should be null. No candidate
template is embedded in the collection or submission command. The test fan
fixture is not used by either command.

Submit that separately authored file in another new trace directory:

```sh
python3 -B -I artifacts/implementation/prompt-intent-handoff/demo/intent_demo.py submit \
  --attempt /absolute/new-submit-attempt \
  --state-dir /absolute/new-live-intent-state \
  --prepared /absolute/new-prepare-attempt \
  --proposal /absolute/external-agent-proposal.json
```

Only the live state directory is mutable across these commands. Earlier attempt
directories remain unchanged. Submission retains the exact supplied file, checked
request/reply, status before/after and identical-key proposal replay. Proposal
replay is a metadata idempotency check; it is not a second application run or a
qualified PAT fast path. All outputs continue to say qualification is unavailable.

Each command creates exclusive trace files and retains source/dependency and
interpreter pins before/after, exact input hashes, monotonic elapsed time, actual
per-process limits, and a success/failure receipt. There is no subprocess or
automatic retry in this command. Limits are 15 CPU seconds, 512 MiB address space,
1 MiB per file, 64 descriptors and core size zero, clamped by existing hard limits.
They do not establish protected control capacity, aggregate quotas or a hostile
sandbox. Neither command imports Runtime, calls hardware, invokes a model,
qualifies/promotes, or executes the proposed PAT.
