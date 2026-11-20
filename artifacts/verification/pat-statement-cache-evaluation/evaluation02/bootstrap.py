"""Pinned standard-library and exact validation-code bootstrap."""
import ast
from collections import OrderedDict
from decimal import Decimal, DecimalException
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import sqlite3
import _sqlite3
import statistics
import sys
import time
import types
from types import FunctionType

BASE = Path(__file__).resolve().parent
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
pins = {row['path']: row for row in json.loads((BASE / 'inputs.json').read_bytes())['files']}


def verify(name):
    path = BASE / name
    row = pins[name]
    assert not path.is_symlink() and path.stat().st_size == row['bytes'] <= 16777216
    body = path.read_bytes()
    assert hashlib.sha256(body).hexdigest() == row['sha256']
    return body


for name in pins:
    verify(name)
external = json.loads(verify('runtime-inputs.json'))
for row in external['files']:
    path = Path(row['path'])
    assert path.stat().st_size == row['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256']
assert sqlite3.sqlite_version == external['sqliteVersion']
assert _sqlite3.__file__ == external['sqliteExtensionOrigin']
denied, connections = [], []


def guard(event, args):
    forbidden = event.startswith('socket.') or event in {
        'subprocess.Popen', 'os.system', 'os.exec', 'os.fork', 'os.forkpty', 'os.posix_spawn',
        'sqlite3.enable_load_extension', 'sqlite3.load_extension'}
    if event == 'sqlite3.connect':
        if args != (':memory:',):
            forbidden = True
        else:
            connections.append(':memory:')
    if event == 'import' and (args[0] == 'hms' or args[0].startswith(('hms.', 'hms_qualification'))):
        forbidden = True
    if event == 'open':
        mode, flags = args[1:3]
        forbidden |= ((type(mode) is str and any(c in mode for c in 'wax+')) or
                      (type(flags) is int and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))))
    if forbidden:
        denied.append(event)
        raise RuntimeError('Evaluation forbids persistent/external execution and I/O')


sys.addaudithook(guard)
sys.path.insert(0, str(BASE / 'vendor'))
import eval_rfc8785 as rfc8785
for module in (rfc8785, rfc8785._impl):
    verify(str(Path(module.__file__).relative_to(BASE)))

# Execute the exact previously reviewed parser/encoder definitions and helpers.
contracts = types.ModuleType('evaluation_contracts')
contracts.__dict__.update(MAX_BYTES=65536, MAX_DEPTH=32, MAX_NODES=16384, SAFE_INTEGER=2**53-1,
    math=math, json=json, Decimal=Decimal, DecimalException=DecimalException, rfc8785=rfc8785)
for name in ('reference_functions.py', 'reference_helpers.py'):
    exec(compile(verify(name), str(BASE / name), 'exec'), contracts.__dict__)
canonical, parse_json = contracts.canonical, contracts.parse_json
assert contracts._fast_allowed()


def definitions(name, wanted):
    tree = ast.parse(verify('references/' + name))
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in wanted]
    assert {n.name for n in nodes} == set(wanted)
    return ast.Module(body=nodes, type_ignores=[])


errors = {}
exec(compile(definitions('journal.py', ['JournalError']), 'exact-journal-error', 'exec'), errors)
exec(compile(definitions('pat_contracts.py', ['PatError', 'require']), 'exact-pat-errors', 'exec'), errors)
cache = dict(OrderedDict=OrderedDict, json=json, FunctionType=FunctionType,
             contracts=contracts, rfc8785=rfc8785, encoder=rfc8785._impl)
cache_tree = ast.parse(verify('references/pat_io_canonical_blobs.py'))
cache_tree.body = [n for n in cache_tree.body if not isinstance(n, (ast.Import, ast.ImportFrom))]
exec(compile(cache_tree, 'exact-canonical-blob-checker', 'exec'), cache)
assert cache['_dependencies_unchanged'](canonical, parse_json)
specifications = json.loads(verify('table-specifications.json'))
TABLES, PROFILE = specifications['TABLES'], specifications['PROFILE']
PUBLIC_META = tuple(specifications['PUBLIC_META'])


def load_method(name):
    tree = ast.parse(verify(name))
    assert len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef)
    namespace = dict(require=errors['require'], canonical=canonical, parse_json=parse_json,
                     CanonicalBlobs=cache['CanonicalBlobs'], PUBLIC_META=PUBLIC_META)
    exec(compile(tree, str(BASE / name), 'exec'), namespace)
    return namespace['_configuration_table']


