"""Build original code only; retain exact inputs and installed build context."""
import hashlib
import inspect
import importlib.machinery
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig

BASE = Path(__file__).resolve().parent
PRIOR = BASE.parent / 'pat-native-retention-prototype'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')

assert sys.version_info[:2] == (3, 12) and sys.platform == 'linux'
assert sha(PRIOR / 'index.json') == '49267a0f05ba173e7b939e48700061e083683a6fce7156dbc7458e70c051a09b'
assert not (BASE / 'build01').exists()
os.umask(0o077)
build = BASE / 'build01'
build.mkdir(mode=0o700)
shutil.copyfile(PRIOR / 'reference.py', BASE / 'reference.py')
with (build / 'installed-loader.py.txt').open('x') as stream:
    stream.write(inspect.getsource(importlib.machinery.ExtensionFileLoader))
compiler = Path(shutil.which('gcc')).resolve()
environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'SOURCE_DATE_EPOCH': '0'}
version = subprocess.run([str(compiler), '--version'], check=True, capture_output=True,
                         env=environment, timeout=10)
rows = []
for kind, source in [('production', 'scanmodule.c'), ('instrumented', 'faultmodule.c')]:
    target = build / kind
    target.mkdir(mode=0o700)
    binary = target / ('_hms_retention_native_v1' + sysconfig.get_config_var('EXT_SUFFIX'))
    argv = [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
            '-fstack-protector-strong', '-D_FORTIFY_SOURCE=2', '-Wl,-z,relro,-z,now',
            '-I' + sysconfig.get_path('include'), str(BASE / source), '-o', str(binary)]
    result = subprocess.run(argv, capture_output=True, env=environment, timeout=30)
    row = dict(kind=kind, argv=argv, returnCode=result.returncode,
               stdout=result.stdout.decode(), stderr=result.stderr.decode(),
               binary=str(binary.relative_to(BASE)), binarySha256=sha(binary) if binary.exists() else None)
    rows.append(row)
    write(target / 'build.json', row)
    assert result.returncode == 0, result.stderr.decode()
write(build / 'receipt.json', dict(builds=rows, environment=environment,
    compiler=str(compiler), compilerSha256=sha(compiler), compilerVersion=version.stdout.decode(),
    python=sys.version, pythonExecutable=str(Path(sys.executable).resolve()),
    pythonExecutableSha256=sha(Path(sys.executable).resolve()),
    extensionSuffix=sysconfig.get_config_var('EXT_SUFFIX'), include=sysconfig.get_path('include'),
    platform=dict(sysname=os.uname().sysname, release=os.uname().release, machine=os.uname().machine),
    fullToolchainClosureAttested=False, instrumentedBuildIsNotProduction=True))
rows = []
for path in sorted(BASE.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        rows.append(dict(path=path.relative_to(BASE).as_posix(), bytes=path.stat().st_size, sha256=sha(path)))
write(BASE / 'inputs.json', dict(scope='Isolated CPython binding inputs before execution', files=rows))
print(json.dumps(dict(inputsSha256=sha(BASE / 'inputs.json'), builds=2)))
