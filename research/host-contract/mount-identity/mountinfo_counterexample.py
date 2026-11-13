"""Synthetic stacked-mount parser example; no mounts or host state are changed."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import resource
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
for key,value in [(resource.RLIMIT_CPU,3),(resource.RLIMIT_AS,128*1024**2),
                  (resource.RLIMIT_FSIZE,1024**2),(resource.RLIMIT_NOFILE,32),(resource.RLIMIT_CORE,0)]:
    resource.setrlimit(key,(value,value))
source=HERE/'fixed_block.reference.py'
wanted='b5173152c5505934275b89a4c1c2e54f4bd4fa75b9a60b8e7f149bd3456b42db'
assert hashlib.sha256(source.read_bytes()).hexdigest()==wanted
spec=importlib.util.spec_from_file_location('hms_mount_parser_reference',source)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.os=SimpleNamespace(fstat=lambda fd:SimpleNamespace(st_dev=os.makedev(8,1)),major=os.major,minor=os.minor)
old='9 1 8:1 /fixture /fixture rw - ext4 /dev/example rw\n'
stacked=old+'100 9 8:1 /fixture /fixture rw - ext4 /dev/example rw\n'
outputs=[]
for body in [old,stacked]:
    module.open=lambda path:io.StringIO(body)
    outputs.append(module._host(Path('/fixture/image'),123))
assert outputs==[(8,'ext4','9'),(8,'ext4','9')]
assert int(stacked.splitlines()[1].split()[1])==9
result=dict(status='counterexample-confirmed',sourceSha256=wanted,source='fixed_block.reference.py',
    testSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),initialMountinfo=old,stackedMountinfo=stacked,
    observedPins=outputs,expectedTopMountIds=['9','100'],pinComparisonDetectsChange=False,
    substitutedFstat=True,substitutedProcFile=True,actualKernelMountChanged=False,actualHostIOPerformed=False)
with (HERE/'COUNTEREXAMPLE.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(result,sort_keys=True))
