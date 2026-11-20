"""Original bounded child fixture; no project imports, hardware or network."""
import json
import os
from pathlib import Path
import signal
import sys
import time

mode, marker=sys.argv[1:]
if mode=='ignore_term':signal.signal(signal.SIGTERM,signal.SIG_IGN)
Path(marker).write_text(json.dumps({'pid':os.getpid(),'mode':mode,'ready':True})+'\n')
print('ORIGINAL_OWNED_CHILD_READY',os.getpid(),mode,flush=True)
# Independent fail-safe if a deliberately broken wrapper loses ownership.
# It is not proof that runner cleanup succeeded; the probe requires runner reaping.
end=time.monotonic()+25
while time.monotonic()<end:time.sleep(0.05)
raise SystemExit(97)
