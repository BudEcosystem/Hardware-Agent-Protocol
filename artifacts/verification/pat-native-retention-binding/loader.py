"""Evaluation loader; assumes the retained build directory is not concurrently modified."""
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import stat
import sys

BASE = Path(__file__).resolve().parent

def load(kind):
    assert kind in ('production', 'instrumented')
    assert sys.platform == 'linux' and sys.version_info[:2] == (3, 12)
    record = json.loads((BASE / 'build01' / kind / 'build.json').read_bytes())
    path = BASE / record['binary']
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['binarySha256']
    name = '_hms_retention_native_v1'
    assert name not in sys.modules
    loader = importlib.machinery.ExtensionFileLoader(name, str(path))
    spec = importlib.util.spec_from_file_location(name, str(path), loader=loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    assert module.ABI_VERSION == 1 and module.__spec__.origin == str(path)
    after = path.lstat()
    assert all(getattr(after, key) == getattr(info, key) for key in
               ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink',
                'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['binarySha256']
    return module
