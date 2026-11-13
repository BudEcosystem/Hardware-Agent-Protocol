"""Local simulation control CLI; no implicit initialization or physical adapter."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys

from .contracts import ContractError, MAX_BYTES, parse_invoke, parse_json
from .api_contracts import ResponseError
from .client import Client
from .ipc import IpcError, PROTOCOL, Server
from .journal import Context, JournalError


def _parser():
    parser = argparse.ArgumentParser(prog='hctl', description='Independent HMS local simulation control')
    parser.add_argument('--socket', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    def command(name):
        sub = commands.add_parser(name)
        sub.add_argument('--socket', type=Path, default=argparse.SUPPRESS)
        return sub
    serve = command('serve')
    serve.add_argument('--state-dir', type=Path, required=True)
    serve.add_argument('--init-simulation', action='store_true')
    discover = command('discover')
    discover.add_argument('--capability')
    discover.add_argument('--limit', type=int, default=20)
    discover.add_argument('--cursor')
    describe = command('describe')
    describe.add_argument('instance')
    describe.add_argument('--digest')
    observe = command('observe')
    observe.add_argument('instance')
    observe.add_argument('property')
    observe.add_argument('--max-age-ms', type=int, required=True)
    observe.add_argument('--evidence-kind', required=True)
    namespace = command('namespace')
    namespace.add_argument('--expires-unix-ms', type=int, required=True)
    invoke = command('invoke')
    invoke.add_argument('--request-file', type=Path, required=True)
    prepare = command('prepare')
    prepare.add_argument('--params-file', type=Path, required=True)
    for name in ('operation', 'events', 'cancel'):
        sub = command(name)
        sub.add_argument('operation')
        if name == 'events':
            sub.add_argument('--after', type=int, default=0)
            sub.add_argument('--limit', type=int, default=100)
    return parser


def _serve(args) -> int:
    from .runtime import Runtime
    owner = Context(f'posix:{os.getuid()}', 'simulation:local') if args.init_simulation else None
    runtime = Runtime(args.state_dir, create=args.init_simulation, owner=owner)
    server = None
    handlers = {}
    try:
        server = Server(runtime, args.socket)
        runtime.start()
        for number in (signal.SIGINT, signal.SIGTERM):
            handlers[number] = signal.getsignal(number)
            signal.signal(number, lambda _number, _frame: server.stop())
        print(json.dumps({'ready': True, 'protocol': PROTOCOL, 'socket': str(server.path),
                          'deployment': runtime.deployment}), flush=True)
        server.serve_forever()
        return 0
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)
        if server is not None:
            server.close()
        runtime.close()


def main(argv=None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.socket is None:
        parser.error('--socket is required')
    try:
        if args.command == 'serve':
            return _serve(args)
        if args.command == 'discover':
            params = {'limit': args.limit}
            if args.capability is not None:
                params['capability'] = args.capability
            if args.cursor is not None:
                params['cursor'] = args.cursor
        elif args.command == 'describe':
            params = {'instanceId': args.instance}
            if args.digest is not None:
                params['digest'] = args.digest
        elif args.command == 'observe':
            params = {'instanceId': args.instance, 'property': args.property,
                      'maxAgeMs': args.max_age_ms, 'evidenceKind': args.evidence_kind}
        elif args.command == 'namespace':
            params = {'expiresUnixMs': args.expires_unix_ms}
        elif args.command == 'invoke':
            with args.request_file.open('rb') as source:
                params = {'request': parse_invoke(source.read(MAX_BYTES + 1))}
        elif args.command == 'prepare':
            with args.params_file.open('rb') as source:
                params = parse_json(source.read(MAX_BYTES + 1))
            if type(params) is not dict:
                raise ContractError('prepare params must be an object')
        else:
            params = {'operationId': args.operation}
            if args.command == 'events':
                params.update(after=args.after, limit=args.limit)
        print(json.dumps(Client(args.socket).request(args.command, params), ensure_ascii=False, allow_nan=False))
        return 0
    except (IpcError, JournalError) as error:
        print(json.dumps({'error': {'code': error.code}}), file=sys.stderr)
        return 1
    except ResponseError:
        print(json.dumps({'error': {'code': 'INVALID_RESPONSE'}}), file=sys.stderr)
        return 1
    except ContractError:
        print(json.dumps({'error': {'code': 'INVALID_REQUEST'}}), file=sys.stderr)
        return 1
    except OSError:
        print(json.dumps({'error': {'code': 'LOCAL_IO_ERROR'}}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
