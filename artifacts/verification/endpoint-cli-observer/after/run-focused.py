import json,sys,unittest
from pathlib import Path
sys.path.insert(0,'tests')
import test_endpoint_cli
suite=unittest.defaultTestLoader.loadTestsFromModule(test_endpoint_cli)
result=unittest.TextTestRunner(verbosity=2).run(suite)
Path(sys.argv[1]).write_text(json.dumps(test_endpoint_cli.LAST_REPORT,indent=2)+'\n')
raise SystemExit(0 if result.wasSuccessful() else 1)
