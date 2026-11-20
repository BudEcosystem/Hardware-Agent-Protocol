"""Standalone reference timing under the same CLI inputs as the C prototype."""
import json
from pathlib import Path
import resource
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from reference import tree_usage,SupervisorError

path=sys.argv[1];maximum_files=int(sys.argv[2]);maximum_bytes=int(sys.argv[3]);repeats=int(sys.argv[4])
def cpu():
    r=resource.getrusage(resource.RUSAGE_SELF)
    return round((r.ru_utime+r.ru_stime)*1000000)
try:
    tree_usage(path,max_files=maximum_files,max_bytes=maximum_bytes)
    started=cpu()
    for _ in range(repeats):result=tree_usage(path,max_files=maximum_files,max_bytes=maximum_bytes)
    elapsed=cpu()-started
    print(json.dumps(dict(reason='OK',errno=0,files=result['files'],logicalBytes=result['logicalBytes'],scans=repeats,cpuMicroseconds=elapsed)))
except (SupervisorError,OSError) as error:
    print(json.dumps(dict(reason=error.code if isinstance(error,SupervisorError) else 'OS_ERROR',errno=error.errno if isinstance(error,OSError) else 0)))
    raise SystemExit(1)
