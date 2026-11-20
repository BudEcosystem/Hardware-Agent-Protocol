"""Update current project prose from the exact stage result, preserving historical evidence."""
import json
from pathlib import Path
ROOT=Path.cwd(); B=ROOT/'artifacts/implementation/pat-io-execution-handoff'
report=json.loads((B/'RESULTS.json').read_bytes()); assert report['goalStatus']=='active' and report['newPassingControlMethods']==50
relative='artifacts/implementation/pat-io-execution-handoff'
def summary(prefix):
    return '''The [durable supervisor handoff candidate]('''+prefix+relative+'''/results/README.md)
passes all **50 new control methods**. It pins an actual durable supervisor
authority and commits the original reservation/request/attempt association before
launch. Replay and recovery preserve that attempt; missing or replaced state does
not authorize a new execution. Five added history controls verify distinct runs,
reopening and retained forged receipt chains with unchanged production source.

Across 349 selected methods, '''+str(report['distinctPassingMethods'])+''' have complete passing receipts and '''+str(report['distinctFailingMethods'])+'''
have complete failing receipts. The 206-method compatibility selection times out
at its original 180-second limit; 194 completed log checks are retained but do not
constitute a complete passing selection. The actual new handoff worker also
reaches its original deadline, before complete matrix inspection and later replay.
Its persisted association is verified; its aggregate effects remain unknown
because one retained state is incomplete. All failed states remain untouched.

The [next integration work]('''+prefix+relative+'''/NEXT.md) is serialized finite-I/O
evidence import and configuration-aware PAT eligibility. This is an isolated
library candidate. Public mounting, protected control capacity, aggregate storage
enforcement, prompt learning, persistent Arduino applications and actual device,
driver and intelligence-hub providers remain required. The full HMS goal is active.
'''
p=ROOT/'PROGRESS.md'; s=p.read_text(); start=s.index('The [canonical-document validation candidate]'); end=s.index('**Latest full regression passed:**',start)
p.write_text(s[:start]+summary('')+'\n'+s[end:])
for name in ('docs/prompt-to-pat.md','docs/io-driver-hub-control.md'):
    p=ROOT/name; s=p.read_text(); assert 'The [durable supervisor handoff candidate]' not in s
    p.write_text(s+'\n\n'+summary('../'))
p=ROOT/'artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'
s=p.read_text(); assert 'pat-io-execution-handoff/results/README.md' not in s
p.write_text(s+'''\n\nThe [durable supervisor handoff candidate](../pat-io-execution-handoff/results/README.md)
adds actual store identity and a Journal-to-original-attempt association before
launch. All 50 new control methods pass; its actual worker and the inherited
206-method compatibility selection retain deadline failures. Complete worker
inspection and later handoff replay are not claimed. Continue with the
[serialized evidence and applicability boundary](../pat-io-execution-handoff/NEXT.md)
while preserving these failures and original limits. Public promotion, protected
capacity, persistent Arduino applications and real device/driver/hub providers
remain open; the full goal remains active.\n''')
print(json.dumps(dict(updated=['PROGRESS.md','docs/prompt-to-pat.md','docs/io-driver-hub-control.md','artifacts/implementation/pat-io-outcome-history/NEXT-QUALIFICATION.md'],goalStatus='active')))
