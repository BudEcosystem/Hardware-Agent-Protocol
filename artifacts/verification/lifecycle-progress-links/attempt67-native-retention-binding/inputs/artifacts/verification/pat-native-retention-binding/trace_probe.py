"""A marked single scan of one owned fixture, using the unchanged production DSO."""
import json
import os
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from loader import load
native = load('production')
mode = sys.argv[1]
assert mode in ('ordinary', 'fifo', 'veto')
target = BASE / 'attempt01' / 'production' / ('empty' if mode == 'veto' else mode)
path = os.fsencode(target)
events = []
class Veto(Exception):
    pass
def audit(event, args):
    if event == 'hms.retention.scan.v1':
        assert args == (path, 8192, 67108864)
        events.append(event)
        if mode == 'veto':
            raise Veto()
sys.addaudithook(audit)
os.write(1, b'HMS_SCAN_BEGIN\n')
try:
    result = native.scan(path, 8192, 67108864)
except Veto:
    result = dict(reason='AUDIT_VETO')
os.write(1, b'HMS_SCAN_END\n')
print(json.dumps(dict(result=result, events=events)))
