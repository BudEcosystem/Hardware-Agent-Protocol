"""One recorded same-key conflict probe in a private configured I/O trial.

The original compiled request is retained. This is an explicit test operation,
not a new-key retry or a public device tool. No admission/effect limit changes.
"""
import copy

from .pat_contracts import require
from .pat_io_configuration_capture import ConfiguredIoTrialEngine
from .procedures import parse_procedure, procedure_digest


class ConflictIoTrialEngine(ConfiguredIoTrialEngine):
    _record_profile = 'hms.pat.io-trial-record/0.2'

    def __init__(self, *args, **kwargs):
        self._conflict_attempted = False
        super().__init__(*args, **kwargs)

    def submit_conflict(self):
        require(self.plan is not None and self.procedure_id is not None, 'PAT_IO_CONFLICT_NOT_SUBMITTED')
        require(not self._conflict_attempted, 'PAT_IO_CONFLICT_ALREADY_ATTEMPTED')
        request = copy.deepcopy(self.plan['request'])
        args = request['procedure']['steps'][0]['request']['intent']['arguments']
        primitive = self.contract['primitive']
        require(primitive in {'gpio_pulse', 'pwm_burst'}, 'PAT_IO_CONFLICT_PRIMITIVE')
        if primitive == 'gpio_pulse':
            args['level'] = 1 - args['level']
        else:
            args['dutyPermille'] = (args['dutyPermille'] + 1) % 1001
        request = parse_procedure(request)
        self._conflict_attempted = True
        self._write('conflict_input', {'phase': self.phase + 1, 'request': request,
            'requestDigest': procedure_digest(request)})
        return self._call('submit_conflict', lambda: self.runtime.procedures.submit(self.owner, request))
