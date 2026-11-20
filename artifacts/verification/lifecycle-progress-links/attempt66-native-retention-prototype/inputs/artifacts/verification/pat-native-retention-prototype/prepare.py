"""Compile the original standalone helper and retain exact reference source."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
REFERENCE=ROOT/'artifacts/verification/pat-retention-scan-cost'
RESEARCH=ROOT/'research/host-contract/native-retention'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
assert not (BASE/'build01').exists()
assert sha(RESEARCH/'index.json')=='b6ba9eaf836ad45f89cd97c8fd20650d9c6dcad0268a1eb563d7982e50d5d61a'
assert sha(REFERENCE/'inputs.json')=='60991fe51d22140c0cb3b9c3811f6471e512108a0c77b764c5e6351b766ce707'
source_rows=json.loads((REFERENCE/'preparation.json').read_bytes())['extracted']
nodes=[ast.Import(names=[ast.alias(name='os')]),ast.Import(names=[ast.alias(name='stat')])]
for row in source_rows:
    if row['name'] not in ('JournalError','SupervisorError','require','tree_usage'):continue
    module=ast.parse((REFERENCE/'references'/row['source']).read_bytes())
    node=next(node for node in module.body if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name==row['name'])
    assert hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()==row['astSha256']
    nodes.append(node)
text=ast.unparse(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])))+'\n'
with (BASE/'reference.py').open('x') as stream:stream.write(text)
compiler=Path(shutil.which('gcc')).resolve();folder=BASE/'build01';folder.mkdir(mode=0o700)
environment={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','SOURCE_DATE_EPOCH':'0'}
version=subprocess.run([str(compiler),'--version'],check=True,capture_output=True,env=environment,timeout=10)
assert len(version.stdout)<=65536 and version.stderr==b''
command=[str(compiler),'-std=c11','-O2','-Wall','-Wextra','-Werror','-fstack-protector-strong','-D_FORTIFY_SOURCE=2',str(BASE/'scan.c'),'-o',str(folder/'scan')]
result=subprocess.run(command,capture_output=True,env=environment,timeout=30)
assert len(result.stdout)+len(result.stderr)<=65536
write(folder/'build.json',dict(argv=command,environment=environment,compiler=str(compiler),compilerSha256=sha(compiler),
    compilerVersion=version.stdout.decode(),sourceSha256=sha(BASE/'scan.c'),returnCode=result.returncode,
    stdout=result.stdout.decode(),stderr=result.stderr.decode(),python=sys.version,
    platform=dict(sysname=os.uname().sysname,release=os.uname().release,machine=os.uname().machine),
    binarySha256=sha(folder/'scan') if (folder/'scan').exists() else None,
    installedCompilerAndSystemHeadersUsed=True,fullToolchainClosureAttested=False,projectRuntimeChanged=False))
assert result.returncode==0,result.stderr.decode()
files=[]
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():files.append(dict(path=path.relative_to(BASE).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
write(BASE/'inputs.json',dict(scope='Standalone Linux prototype and reference; frozen before execution',files=files))
print(json.dumps(dict(binaryBytes=(folder/'scan').stat().st_size,binarySha256=sha(folder/'scan'),inputsSha256=sha(BASE/'inputs.json'))))
