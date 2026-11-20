"""Five independent original failure/interruption scopes, each attempted once."""
import subprocess,sys
from pathlib import Path
B=Path('artifacts/implementation/pat-io-execution-handoff')
for number in range(19,24):
    done=subprocess.run([sys.executable,'-I','-B',str(B/'run-process-selection.py'),str(number)])
    if done.returncode:raise SystemExit(done.returncode)
