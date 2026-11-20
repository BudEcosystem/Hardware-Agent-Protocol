"""Local simulation control CLI; no implicit initialization or physical adapter."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys

from .contracts import ContractError, MAX_BYTES, identifier, parse_invoke, parse_json
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
    initialization = serve.add_mutually_exclusive_group()
    initialization.add_argument('--init-simulation', action='store_true')
    initialization.add_argument('--init-compact-simulation', action='store_true')
    initialization.add_argument('--init-multi-simulation', action='store_true')
    serve.add_argument('--installations-file', type=Path, help='Bounded JSON list of installed simulation routes')
    serve.add_argument('--endpoint-fd', type=int, help='Inherited connected Unix stream for the original compact C simulator')
    serve.add_argument('--endpoint-route', action='append', default=[], metavar='ADAPTER=FD',
                       help='Inherited connected Unix stream for a named compact simulation route; repeatable')
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
    procedure = command('procedure-submit')
    procedure.add_argument('--request-file', type=Path, required=True)
    for name in ('procedure-status', 'procedure-cancel', 'procedure-resume', 'procedure-events'):
        sub = command(name)
        sub.add_argument('procedure')
        if name == 'procedure-events':
            sub.add_argument('--after', type=int, default=0)
            sub.add_argument('--limit', type=int, default=100)
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
    if args.init_compact_simulation and args.endpoint_fd is None or args.init_simulation and args.endpoint_fd is not None:
        raise JournalError('INVALID_ENDPOINT_INITIALIZATION')
    if ((args.init_multi_simulation and (args.installations_file is None or args.endpoint_fd is not None)) or
            ((args.init_simulation or args.init_compact_simulation) and
             (args.installations_file is not None or args.endpoint_route))):
        raise JournalError('INVALID_ENDPOINT_INITIALIZATION')
    installations = None
    if args.installations_file is not None:
        with args.installations_file.open('rb') as source:
            installations = parse_json(source.read(MAX_BYTES + 1))
    routes = {}
    for value in args.endpoint_route:
        adapter, separator, descriptor = value.partition('=')
        if not separator or not descriptor.isascii() or not descriptor.isdecimal() or len(descriptor) > 10:
            raise JournalError('INVALID_ENDPOINT_ROUTES')
        identifier(adapter)
        if adapter in routes:
            raise JournalError('DUPLICATE_ENDPOINT_ROUTE')
        routes[adapter] = int(descriptor)
    create = args.init_simulation or args.init_compact_simulation or args.init_multi_simulation
    deployment = ('simulation:multi' if args.init_multi_simulation else
                  'simulation:compact' if args.endpoint_fd is not None else 'simulation:local')
    owner = Context(f'posix:{os.getuid()}', deployment) if create else None
    runtime = Runtime(args.state_dir, create=create, owner=owner, endpoint_fd=args.endpoint_fd,
                      installations=installations, endpoint_fds=routes)
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
        elif args.command == 'procedure-submit':
            from .procedures import parse_procedure
            with args.request_file.open('rb') as source:
                params = {'request': parse_procedure(parse_json(source.read(MAX_BYTES + 1)))}
        elif args.command.startswith('procedure-'):
            params = {'procedureId': args.procedure}
            if args.command == 'procedure-events':
                params.update(after=args.after, limit=args.limit)
        elif args.command == 'prepare':
            with args.params_file.open('rb') as source:
                params = parse_json(source.read(MAX_BYTES + 1))
            if type(params) is not dict:
                raise ContractError('prepare params must be an object')
        else:
            params = {'operationId': args.operation}
            if args.command == 'events':
                params.update(after=args.after, limit=args.limit)
        print(json.dumps(Client(args.socket).request(args.command.replace('-', '_'), params), ensure_ascii=False, allow_nan=False))
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
