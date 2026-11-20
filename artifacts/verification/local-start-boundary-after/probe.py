"""Read-only production probe: original local SQLite simulation, controlled time.

Creates only temporary runtime stores. Production sources and test suites are
not modified. No physical device, controller binary, or model is executed.
"""
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from hms.journal import Context, JournalError
from hms.runtime import Runtime


class StatementDelay:
    def __init__(self, connection, statement, action):
        self.connection, self.statement, self.action = connection, statement, action
        self.fired = False

    def __getattr__(self, key):
        return getattr(self.connection, key)

    def execute(self, sql, *args, **kwargs):
        result = self.connection.execute(sql, *args, **kwargs)
        if sql == self.statement and not self.fired:
            self.fired = True
            self.action()
        return result


def run(mode):
    clock = {'wall': 4999, 'mono': 4999}
    milestones = []

    def delay():
        clock['wall'] += 2000
        clock['mono'] += 2000
        milestones.append({'phase': mode, **clock})

    def invalid_clock():
        clock['wall'] = True
        milestones.append({'phase': mode, **clock})

    def regressed_clock():
        clock['wall'] = 3999
        milestones.append({'phase': mode, **clock})

    owner = Context('start-probe', 'simulation:local')
    with tempfile.TemporaryDirectory() as directory:
        runtime = Runtime(directory, create=True, owner=owner,
            wall_clock_ms=lambda: clock['wall'], monotonic_ms=lambda: clock['mono'])
        try:
            adapter = runtime.adapters['simulator:local']
            namespace = runtime.request(owner, 'namespace', {'expiresUnixMs': 30000})['token']
            request = runtime.request(owner, 'prepare', {
                'instanceId': 'sim:home-fan', 'actionId': 'set_level',
                'arguments': {'level': 37, 'unit': 'percent'},
                'operationKey': 'start-probe:one', 'replayNamespace': namespace,
                'requiredEffect': 'capability_completion',
                'timing': {'notBeforeUnixMs': 4999, 'latestStartUnixMs': 5000,
                           'maxRunMs': 4000, 'latestCompletionUnixMs': 20000}})['request']
            operation = runtime.request(owner, 'invoke', {'request': request})
            original_claim = runtime.journal.claim_dispatch
            original_begin = adapter.plant.begin

            def claim(*args, **kwargs):
                if mode == 'claim_commit_delay':
                    with patch.object(runtime.journal, '_db',
                            StatementDelay(runtime.journal._db, 'COMMIT', delay)):
                        ticket = original_claim(*args, **kwargs)
                else:
                    ticket = original_claim(*args, **kwargs)
                milestones.append({'phase': 'claim_returned', **clock})
                return ticket

            def begin(*args, **kwargs):
                milestones.append({'phase': 'plant_begin_entered', **clock})
                action = {'plant_begin_delay': delay,
                          'plant_begin_invalid_clock': invalid_clock,
                          'plant_begin_regressed_clock': regressed_clock}.get(mode)
                if action:
                    with patch.object(adapter.plant, 'db',
                            StatementDelay(adapter.plant.db, 'BEGIN IMMEDIATE', action)):
                        receipt = original_begin(*args, **kwargs)
                else:
                    receipt = original_begin(*args, **kwargs)
                milestones.append({'phase': 'plant_begin_returned', 'receiptState': receipt['state'], **clock})
                return receipt

            error = None
            with patch.object(runtime.journal, 'claim_dispatch', claim), patch.object(adapter.plant, 'begin', begin):
                try:
                    adapter.tick()
                    if mode == 'control':
                        clock['wall'] += 100
                        clock['mono'] += 100
                        adapter.tick()
                except JournalError as caught:
                    error = caught.code
            status = runtime.request(owner, 'operation', {'operationId': operation['operationId']})
            replay = runtime.request(owner, 'invoke', {'request': request})
            return {'case': mode, 'timing': request['intent']['timing'], 'milestones': milestones,
                'status': status, 'receipt': adapter.plant.receipt(operation['operationId']),
                'effectCount': adapter.plant.observe('sim:home-fan')['effectCount'],
                'clockFloor': int(runtime.journal._meta('last_clock')),
                'replaySameOperation': replay['operationId'] == operation['operationId'],
                'tickError': error}
        finally:
            runtime.close()


if __name__ == '__main__':
    cases = [run(mode) for mode in ('control', 'claim_commit_delay', 'plant_begin_delay',
        'plant_begin_invalid_clock', 'plant_begin_regressed_clock')]
    print(json.dumps({'profile': 'hms.local-start-boundary-probe/0.1', 'cases': cases}, indent=2))
