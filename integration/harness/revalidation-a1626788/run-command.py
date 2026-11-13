#!/usr/bin/env python3
"""Run one review command with worktree-owned package-manager storage and no credentials."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path('/home/bud/Desktop/bud/hms-harness-a1626788')
HERE = Path(__file__).resolve().parent
state = ROOT / '.task-state'
env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ('KEY', 'SECRET', 'TOKEN', 'PASSWORD'))}
env.update(PATH='/home/bud/.nvm/versions/node/v24.22.1/bin:' + env['PATH'], CI='true',
           XDG_STATE_HOME=str(state / 'state'), XDG_CONFIG_HOME=str(state / 'config'), XDG_CACHE_HOME=str(state / 'cache'),
           pnpm_config_store_dir=str(state / 'pnpm-store'), pnpm_config_cache_dir=str(state / 'pnpm-cache'),
           pnpm_config_npmrc_auth_file=str(state / 'empty.npmrc'), pnpm_config_verify_deps_before_run='false')
name, *args = sys.argv[1:]
if args[0] == 'pnpm':
    args = ['node', '/home/bud/.local/share/pnpm/.tools/pnpm/11.28.5/node_modules/pnpm/bin/pnpm.mjs', *args[1:]]
started = time.monotonic()
with (HERE / 'verification' / (name + '.log')).open('w') as output:
    result = subprocess.run(args, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT)
record = {'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'argv': args, 'cwd': str(ROOT),
          'exit_code': result.returncode, 'elapsed_seconds': round(time.monotonic() - started, 3),
          'test_environment': {key: env[key] for key in ('HMS_ROOT', 'HMS_CAPTURE', 'HMS_TIMINGS', 'HMS_SDK_CAPTURE', 'HMS_COMPACT_ROOT', 'HMS_COMPACT_CAPTURE', 'HMS_COMPACT_DIAGNOSTICS') if key in env},
          'environment': 'Credential names scrubbed; private XDG state/config/cache and pnpm store/cache/auth config; Node24.22.1 first in PATH; automatic pre-run install disabled after explicit installation.'}
(HERE / 'verification' / (name + '.command.json')).write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps(record))
raise SystemExit(result.returncode)
