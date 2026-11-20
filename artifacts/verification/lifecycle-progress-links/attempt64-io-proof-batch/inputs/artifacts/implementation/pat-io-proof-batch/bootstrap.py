"""Create a fresh uninstrumented candidate; no project code executes here."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
SOURCE=ROOT/'artifacts/implementation/pat-vault-original-run/implementation02'
STAGE=BASE/'implementation01';PROJECT=STAGE/'project'
PIN='4a1f5b97cb29e897fc865ca5dcf46397bfdec6c4154a302dfdac1b546e66c4f4'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_bytes())
def write(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(body if type(body)is bytes else body.encode())
def dump(path,value):write(path,json.dumps(value,indent=2)+'\n')
assert sha(SOURCE/'index.json')==PIN and not STAGE.exists()
baseline=[]
for row in read(SOURCE/'index.json')['files']:
    path=ROOT/row['path'];assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    if path.is_relative_to(SOURCE/'project'):
        relative=path.relative_to(SOURCE/'project');write(PROJECT/relative,path.read_bytes())
        baseline.append(dict(path=relative.as_posix(),bytes=row['bytes'],sha256=row['sha256']))
assert len(baseline)==286
dump(STAGE/'baseline-inputs.json',dict(sourceIndexSha256=PIN,files=baseline))
topology=PROJECT/'hms/resource_topology.py';original_topology=topology.read_text()
proof_node=next(n for n in ast.parse(original_topology).body if isinstance(n,ast.FunctionDef) and n.name=='binding_proof')
proof=ast.get_source_segment(original_topology,proof_node)
marker='    details = {row["actionId"]:'
assert proof.count(marker)==1
split=proof.index(marker);head,tail=proof[:split],proof[split:]
replacement=head+'    return _binding_proof_from_validated(document, current, instance_id, consumers, atoms, closures)\n\n\n'
replacement+='def _binding_proof_from_validated(document, current, instance_id, consumers, atoms, closures):\n'+tail
replacement+='''


class _BindingProofBuild:
    """One pure definition call's detached static snapshot; never live authority.

    Construction is lazy so the original first-handler refusal order remains.
    The enclosing pure build must not mutate its input or validation helpers.
    This private object must not escape that build or serve public proof calls.
    """
    __slots__ = ('topology', 'generations', 'document', 'current', 'atoms', 'closures')

    def __init__(self, topology, generations):
        self.topology, self.generations = topology, generations
        self.document = self.current = self.atoms = self.closures = None

    @_errors
    def __call__(self, instance_id):
        identifier(instance_id)
        if self.document is None:
            document = parse_topology(self.topology)
            current = _generations(document, self.generations)
            self.document, self.current = document, current
        document, current = self.document, self.current
        consumers = [row for row in document["consumers"] if row["instanceId"] == instance_id]
        _require(consumers, "RESOURCE_UNKNOWN_CONSUMER")
        if self.atoms is None:
            atoms, closures = _atom_index(document), _alias_closures(document)
            self.atoms, self.closures = atoms, closures
        return _binding_proof_from_validated(document, current, instance_id, consumers, self.atoms, self.closures)
'''
assert original_topology.count(proof)==1
topology.write_text(original_topology.replace(proof,replacement))
installation=PROJECT/'hms/synthetic_io_installation.py';original_installation=installation.read_text()
definitions_node=next(n for n in ast.parse(original_installation).body if isinstance(n,ast.FunctionDef) and n.name=='definitions')
definitions=ast.get_source_segment(original_installation,definitions_node)
updated=original_installation.replace("MAX_DURATION_MS = 5000\n", "MAX_DURATION_MS = 5000\n_DEFINITION_BINDING_PROOF = binding_proof\n")
updated=updated.replace('def _handler_details(document, instance, action, proof):','def _handler_details(document, instance, action, proof, build=None):')
old="    if proof is None:\n        proof = binding_proof(topology, document['initialGenerations'], instance)"
new="""    if proof is None:
        if build is None or binding_proof is not _DEFINITION_BINDING_PROOF:
            proof = binding_proof(topology, document['initialGenerations'], instance)
        else:
            # This cell belongs only to the enclosing pure definitions() call.
            # First-handler lookup still precedes all topology validation.
            if build[0] is None:
                build[0] = _topology._BindingProofBuild(topology, document['initialGenerations'])
            proof = build[0](instance)"""
assert updated.count(old)==1;updated=updated.replace(old,new)
new_definitions=definitions.replace('    result = {}','    result = {}; build = [None]').replace('_handler_details(document, instance, action, proof)','_handler_details(document, instance, action, proof, build)')
assert updated.count(definitions)==1;updated=updated.replace(definitions,new_definitions)
installation.write_text(updated)
# Reference functions retain the exact baseline AST, except their names.
reference='''"""Exact baseline bodies for independent differential comparison."""
import copy
import hashlib
from hms.synthetic_io_installation import (_handler_details, type_bundle, argument_schema,
    validate_type_bundle, control_generation)
from hms.resource_topology import (_errors, identifier, parse_topology, _generations,
    _require, _atom_index, _alias_closures, _consumer_details, _hash,
    PROOF_PROFILE, _VALIDATORS, canonical)

'''
reference+=definitions.replace('def definitions(', 'def reference_definitions(',1)+'\n\n\n@_errors\n'
reference+=proof.replace('def binding_proof(', 'def reference_binding_proof(',1)+'\n'
write(PROJECT/'tests/_reference_definition_build.py',reference)
# Preserve the old semantic assertions; count the factored per-instance derivation.
path=PROJECT/'tests/test_pat_io_definition_build.py';text=path.read_text()
assert text.count('function = module.binding_proof.__wrapped__')==4
text=text.replace('function = module.binding_proof.__wrapped__','function = module._topology._binding_proof_from_validated',3)
path.write_text(text)
# Recompute the literal original-run consumer pin independently from the exact
# previously audited image inventory, substituting current project bytes.
prior=ROOT/'artifacts/implementation/pat-vault-original-run'
assert sha(prior/'index.json')=='0c64dd5e444f273e8fe9e4caf09b46fdfa4e9cdd310d7d66ffb07d09f9f3ef7b'
report=read(prior/'RESULTS.json')
attempt=prior/'harness03/attempts/attempt01-actual'
work=attempt/'scratch/test_actual_original_matrix_import_and_cold_vault_history'
images=[p for p in (work/'supervisor').glob('code-*') if p.is_dir()];assert len(images)==1
image=images[0];archive_rows={row['path']:row for row in read(attempt/'scratch-index.json')}
source_rows=[]
for path in sorted(image.rglob('*')):
    if not path.is_file():continue
    row=archive_rows[path.relative_to(attempt/'scratch').as_posix()]
    assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256']
    relative=path.relative_to(image).as_posix()
    selected=path if relative.startswith('dependencies/') else PROJECT/relative
    source_rows.append(dict(path=relative,bytes=selected.stat().st_size,sha256=sha(selected)))
assert len(source_rows)==262
def package(package,names):
    return [dict(path=package+'/'+name,bytes=(PROJECT/package/name).stat().st_size,sha256=sha(PROJECT/package/name)) for name in names]
def digest(domain,value):
    # These metadata trees contain only ASCII keys/values and bounded integers.
    body=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    assert body.isascii()
    return 'sha256:'+hashlib.sha256(domain+b'\0'+body).hexdigest()
source_rows+=package('evidence',('__init__.py','contracts.py','archive.py','reducer.py','store.py'))
legacy=digest(b'HMS-PAT-IO-EVIDENCE-CONSUMER-v0.1',sorted(source_rows,key=lambda r:r['path']))
vault=digest(b'HMS-PAT-EVIDENCE-VAULT-IMPLEMENTATION-v0.1',dict(legacyIdentity=legacy,sources=package('evidence_vault',('__init__.py','contracts.py','connection.py','store.py'))))
consumer=digest(b'HMS-PAT-VAULT-IMPORT-IMPLEMENTATION-v0.1',dict(vaultIdentity=vault,sources=package('evidence_authority',('__init__.py','contracts.py','store.py'))))
path=PROJECT/'tests/test_vault_original_run.py';text=path.read_text()
old='sha256:0e7ff6440fdb93e941ff4b5b0f2f275558f67f1e63a3c719c66756f81b7971d5'
assert text.count(old)==1;path.write_text(text.replace(old,consumer))
dump(STAGE/'identity-pins.json',dict(legacy=legacy,vault=vault,consumer=consumer,producerImageFiles=262,sourceRows=source_rows,
    actualRuntimeEqualityStillRequiresExecution=True))
for name in ('hms/resource_topology.py','hms/synthetic_io_installation.py','tests/test_pat_io_definition_build.py','tests/test_vault_original_run.py'):
    old=(SOURCE/'project'/name).read_text();new=(PROJECT/name).read_text()
    write(BASE/'patches'/(Path(name).name+'.patch'),''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='baseline/'+name,tofile='candidate/'+name)))
for path in PROJECT.rglob('*.py'):ast.parse(path.read_bytes())
print(json.dumps(dict(projectFiles=sum(p.is_file() for p in PROJECT.rglob('*')),productionChanged=['hms/resource_topology.py','hms/synthetic_io_installation.py'],consumer=consumer,projectExecuted=False)))
