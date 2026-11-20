#!/usr/bin/env python3
"""Retain actual modern/legacy MCP -> compact native endpoint integration evidence.

Uses the already built original native fixture and installed MCP SDK 1.26.0 as
a legacy client tester. No download, install, device, target execution or build.
Existing MCP/endpoint verification artifacts are read without modification.
"""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'artifacts/verification/compact-mcp'
BINARY = 'artifacts/verification/endpoint-scenarios-build/endpoint-scenarios-pipe'
BUILD_RECEIPT = 'artifacts/verification/endpoint-scenarios.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def record(path):
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path), 'bytes': path.stat().st_size}


def tester_dependencies():
    result = []
    for name in ('mcp', 'anyio', 'jsonschema', 'jsonschema-specifications', 'referencing',
                 'rpds-py', 'attrs', 'pydantic', 'pydantic-core', 'typing-extensions'):
        distribution = importlib.metadata.distribution(name)
        metadata = [Path(distribution.locate_file(path)) for path in distribution.files
                    if str(path).endswith('.dist-info/METADATA')]
        result.append({'name': name, 'version': distribution.version,
                       'metadata': [{'path': str(path), 'sha256': sha(path)} for path in metadata]})
    sdk = importlib.metadata.distribution('mcp')
    assert sdk.version == '1.26.0', 'This bounded legacy receipt requires installed SDK 1.26.0'
    files = [Path(sdk.locate_file(path)) for path in sdk.files
             if str(path).startswith('mcp/') and str(path).endswith('.py')]
    return {'role': 'Installed legacy SDK tester only; production projection has no SDK dependency.',
            'distributions': result,
            'sdkPythonFiles': [{'path': str(path), 'sha256': sha(path)} for path in sorted(files)],
            'qualification': 'Hashes identify installed SDK sources, not a full source-reading claim or hermetic dependency closure.'}


def input_paths(build):
    selected = {ROOT / item['path'] for item in build['files']}
    selected.update(ROOT.glob('hms/**/*.py'))
    selected.update(ROOT.glob('schemas/*.json'))
    selected.update(ROOT.glob('examples/wot/*.json'))
    selected.update(ROOT / relative for relative in (
        BINARY, BUILD_RECEIPT, 'scripts/check_compact_mcp.py',
        'tests/test_endpoint_mcp.py', 'tests/test_endpoint_cli.py', 'tests/__init__.py',
        'research/mcp/raw/schema__2026-07-28__schema.json',
        'research/protocols/wot-artifacts/td-schema-1.1.json'))
    return sorted(path for path in selected if path.is_file())


def main():
    assert sys.platform == 'linux', 'Linux inherited Unix sockets and peer credentials required'
    assert not sys.flags.optimize, 'Assertions must remain enabled in this verification'
    DESTINATION.mkdir(parents=True, exist_ok=True)
    build = json.loads((ROOT / BUILD_RECEIPT).read_text())
    assert build['passed'] is True
    for item in build['files']:
        assert sha(ROOT / item['path']) == item['sha256'], f"Native build input changed: {item['path']}"
    binary_record = next(item for item in build['outputs'] if item['path'] == BINARY)
    assert sha(ROOT / BINARY) == binary_record['sha256'], 'Native binary differs from retained build receipt'
    compiler = Path(build['compiler']['path'])
    assert sha(compiler) == build['compiler']['sha256'], 'Retained native compiler identity changed'
    dependencies = tester_dependencies()
    inputs = [record(path) for path in input_paths(build)]
    command = [sys.executable, '-B', '-m', 'unittest', 'tests.test_endpoint_mcp', '-v']
    trace_directory = DESTINATION / 'traces'
    trace_directory.mkdir(exist_ok=True)
    # A missing new trace cannot be satisfied by an earlier successful run.
    for version in ('2025-11-25', '2026-07-28'):
        (trace_directory / f'{version}.json').unlink(missing_ok=True)
    environment = os.environ.copy()
    environment['HMS_COMPACT_MCP_TRACE_DIR'] = str(trace_directory)
    report = {'schema': 'hms.compact-mcp-verification/1', 'passed': False, 'startedUtc': stamp(),
              'command': command, 'cwd': str(ROOT), 'inputs': inputs,
              'nativeBuildReceipt': BUILD_RECEIPT, 'nativeBinary': binary_record,
              'nativeCompiler': build['compiler'], 'testerDependencies': dependencies,
              'python': {'path': str(Path(sys.executable).resolve()), 'sha256': sha(Path(sys.executable).resolve()),
                         'version': sys.version}, 'platform': platform.platform(),
              'scope': 'Actual MCP stdio clients -> projection processes -> separate Unix-IPC HMS daemon -> original native C framed endpoint; synthetic effects only.',
              'limitations': [
                  '2026-07-28 is an original raw-wire client checked against the retained official schema; no modern third-party SDK interoperability claim.',
                  '2025-11-25 uses installed MCP SDK 1.26.0; no installation or acquired endpoint implementation execution.',
                  'Same Unix UID shares authority. MCP identities/request IDs do not establish per-agent or remote authorization.',
                  'No physical ports, MCU/target execution, qualified NVM, independent stop, hardware timing or physical verification.',
                  'Each run uses native CLOCK_MONOTONIC with no deterministic control FD. Fan/focus values are idempotent; exact OP frames prove handoff count, not independent physical effect count.',
                  'Inspection counter1 is native synthetic state. Native receipt bytes are independently decoded and compared with MCP results.',
                  'MCP close versus explicit cancel is exercised for accepted future host work before dispatch; no running cancellation/rollback guarantee.',
                  'Host SIGKILL is exercised in the modern path after endpoint admission and before durable receipt consumption; endpoint process/socket survive and test owner reclaims its known stale IPC pathname.',
                  'SDK context close does not expose the child return code; stderr is checked, a new projection reads the admitted operation, and its endpoint remains alive.',
                  'Fresh temporary authorities and process memory only; arbitrary database rollback, machine reboot and physical recovery are outside this evidence.'
              ]}
    started = time.monotonic()
    try:
        process = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, timeout=180)
        (DESTINATION / 'tests.stdout.log').write_bytes(process.stdout)
        (DESTINATION / 'tests.stderr.log').write_bytes(process.stderr)
        report['exitCode'] = process.returncode
        assert process.returncode == 0, process.stderr.decode(errors='replace')
        assert b'Ran 2 tests' in process.stderr and b'OK' in process.stderr and b'skipped=' not in process.stderr
        for item in inputs:
            assert sha(ROOT / item['path']) == item['sha256'], f"Input changed during integration: {item['path']}"
        traces = [json.loads((trace_directory / f'{version}.json').read_text())
                  for version in ('2025-11-25', '2026-07-28')]
        assert all(trace['passed'] and len(trace['scenarios']) == 3 and
                   trace['independentEvidence']['forwardedOpFrames'] == 3 for trace in traces)
        assert traces[1]['hostProcessLoss']['matchingRecoveryQuery']
        assert traces[1]['hostProcessLoss']['noOpRetransmission']
        assert traces[0]['catalogs'][0]['schemas'] == traces[1]['catalogs'][0]['schemas']
        report['summary'] = {
            'testCases': 2, 'scenarioExecutions': 6, 'protocols': [trace['protocol'] for trace in traces],
            'validatedToolReplies': sum(trace['validatedToolReplies'] for trace in traces),
            'originalOpFrames': sum(trace['independentEvidence']['forwardedOpFrames'] for trace in traces),
            'schemasIdenticalAcrossNegotiatedProtocols': True, 'deliberateExactReplay': True,
            'mcpProcessCloseDoesNotCancelFutureHostWork': True, 'explicitHmsCancelBeforeDispatch': True,
            'modernHostSigkillRecoversByQueryWithoutOpReplay': True}
        snapshots = []
        for item in inputs:
            destination = DESTINATION / 'inputs' / item['path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / item['path'], destination)
            assert sha(destination) == item['sha256']
            snapshots.append(record(destination))
        report['inputSnapshots'] = snapshots
        report['passed'] = True
    except BaseException as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        report['elapsedSeconds'] = round(time.monotonic() - started, 3)
        report['finishedUtc'] = stamp()
        report['outputs'] = [record(path) for path in sorted([
            *trace_directory.glob('*.json'), *DESTINATION.glob('tests.*.log')])]
        (DESTINATION / 'verification.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed': report['passed'], **report['summary'],
                      'receipt': str((DESTINATION / 'verification.json').relative_to(ROOT))}, sort_keys=True))


if __name__ == '__main__':
    main()
