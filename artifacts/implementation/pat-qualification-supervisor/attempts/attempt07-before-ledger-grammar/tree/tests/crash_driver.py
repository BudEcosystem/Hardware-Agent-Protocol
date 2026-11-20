"""Original test driver: real process loss at a private supervisor checkpoint."""
import json
import os
from pathlib import Path
import sys

from qualification_supervisor import QualificationSupervisor
from hms import pat_simulation_worker as worker

root, source, phase = sys.argv[1:]
expected = Path(os.environ['EXPECTED_HMS_ROOT']).resolve()
assert worker._ROOT.resolve() == expected, (worker._ROOT, expected)
supervisor = QualificationSupervisor(root, create=True)
def crash(here, row):
    if here == phase: os._exit(91)
supervisor._checkpoint = crash
supervisor.execute(json.loads(Path(source).read_bytes()))
raise AssertionError('crash checkpoint not reached')
