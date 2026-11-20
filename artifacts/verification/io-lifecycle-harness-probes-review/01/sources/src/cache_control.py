"""Original harmless counterfactual: cached bytecode is loadable before veto."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
sys.path.insert(0,sys.argv[1])
import probe_source
value={'value':probe_source.VALUE,'modulePath':probe_source.__file__,'cachePath':probe_source.__cached__}
Path(sys.argv[2]).write_text(json.dumps(value,indent=2)+'\n')
raise SystemExit(0 if probe_source.VALUE=='cached' else 1)
