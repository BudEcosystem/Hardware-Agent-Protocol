import json,sys,unittest
from pathlib import Path
sys.path.insert(0,'tests')
from hms.pat_compiler import compiler_digest,compiler_manifest
Path(sys.argv[1]).write_text(json.dumps({'compilerDigest':compiler_digest(),'manifest':compiler_manifest()},indent=2)+'\n')
import test_pat_execution
suite=unittest.defaultTestLoader.loadTestsFromModule(test_pat_execution)
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
