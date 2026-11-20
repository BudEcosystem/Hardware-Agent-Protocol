"""Harness-only observations; no PID lookup, extra wait, or scheduling change."""
import os
import resource
import stat
import time


_RU_FIELDS = ('ru_utime', 'ru_stime', 'ru_maxrss', 'ru_ixrss', 'ru_idrss',
    'ru_isrss', 'ru_minflt', 'ru_majflt', 'ru_nswap', 'ru_inblock',
    'ru_oublock', 'ru_msgsnd', 'ru_msgrcv', 'ru_nsignals', 'ru_nvcsw', 'ru_nivcsw')
_ADDITIVE_FIELDS = ('ru_utime', 'ru_stime', 'ru_minflt', 'ru_majflt',
    'ru_inblock', 'ru_oublock', 'ru_nvcsw', 'ru_nivcsw')


def _pressure_read(path):
    with open(path, 'rb') as stream:
        body = stream.read(4097)
    if len(body) > 4096:
        raise ValueError('Pressure file exceeds 4096-byte observation bound')
    return body.decode('ascii')


def _usage_snapshot(get_usage=resource.getrusage, clock=time.monotonic_ns,
                    read_pressure=_pressure_read):
    value = {'beforeMonotonicNs': clock(), 'usage': {}, 'pressure': {}}
    for name, selector in (('self', resource.RUSAGE_SELF), ('children', resource.RUSAGE_CHILDREN)):
        try:
            usage = get_usage(selector)
            value['usage'][name] = {'available': True,
                'raw': {field: getattr(usage, field) for field in _RU_FIELDS}}
        except Exception as error:
            value['usage'][name] = {'available': False, 'errorType': type(error).__name__}
    for name in ('cpu', 'memory', 'io'):
        try:
            raw = read_pressure('/proc/pressure/' + name)
            if type(raw) is not str or len(raw.encode('ascii')) > 4096:
                raise ValueError('Pressure observation is not bounded ASCII text')
            value['pressure'][name] = {'available': True, 'raw': raw}
        except Exception as error:
            value['pressure'][name] = {'available': False, 'errorType': type(error).__name__}
    value['afterMonotonicNs'] = clock()
    return value


def _usage_delta(before, after):
    result = {}
    for scope in ('self', 'children'):
        first, last = before['usage'][scope], after['usage'][scope]
        if not first['available'] or not last['available']:
            result[scope] = {'available': False}
            continue
        counters = {field: last['raw'][field] - first['raw'][field] for field in _ADDITIVE_FIELDS}
        if any(value < 0 for value in counters.values()):
            result[scope] = {'available': False, 'reason': 'counter_regression'}
            continue
        result[scope] = {'available': True, 'additiveCounters': counters}
    return result


def _descriptor_identity(fd, get_stat=os.fstat):
    try:
        info = get_stat(fd)
        return {'available': True, 'descriptor': fd, 'device': info.st_dev,
            'inode': info.st_ino, 'uid': info.st_uid, 'mode': stat.S_IMODE(info.st_mode),
            'fileType': stat.S_IFMT(info.st_mode), 'size': info.st_size}
    except Exception as error:
        return {'available': False, 'descriptor': fd, 'errorType': type(error).__name__}


class _WorkerAccounting:
    def __init__(self, snapshot=_usage_snapshot, clock=time.monotonic_ns,
                 identify=_descriptor_identity, persist=lambda name, value: None):
        self.snapshot, self.clock, self.identify, self.persist = snapshot, clock, identify, persist
        self.test_id = None
        self.start = self.finish = None
        self.launch = None
        self.process = None
        self.errors = []

    def note_error(self, phase, error):
        if len(self.errors) < 32:
            self.errors.append({'phase': phase, 'errorType': type(error).__name__})

    def emit(self, name):
        try:
            self.persist(name, self.report())
        except Exception as error:
            self.note_error('persist:' + name, error)

    def start_test(self, test_id):
        if self.start is not None:
            raise RuntimeError('Exactly one original test is permitted')
        self.test_id = test_id
        self.start = self.snapshot()
        self.emit('worker-accounting-start.json')

    def before_launch(self, argv):
        if self.start is None or self.launch is not None:
            raise RuntimeError('Exactly one original launch is permitted')
        # The unchanged subprocess audit separately validates the complete argv.
        if type(argv) not in (list, tuple) or len(argv) != 7:
            raise RuntimeError('Unexpected original worker arguments')
        descriptors = {name: self.identify(int(argv[index])) for name, index in
            (('attemptDirectory', 4), ('input', 5), ('writerLease', 6))}
        self.launch = {'argv': list(argv), 'descriptors': descriptors,
            'before': self.snapshot(), 'pid': None, 'launchedMonotonicNs': None,
            'terminal': None, 'launchFailure': None}
        self.emit('worker-accounting-launch.json')

    def launched(self, process):
        self.process = process
        self.launch['pid'] = process.pid
        self.launch['launchedMonotonicNs'] = self.clock()

    def failed_launch(self, error):
        self.launch['launchFailure'] = type(error).__name__
        self.emit('worker-accounting-launch-failed.json')

    def observed_return(self, process, code, via):
        if process is not self.process:
            self.note_error('foreign-process-object', RuntimeError())
            return
        if code is None or self.launch['terminal'] is not None:
            return
        self.launch['terminal'] = {'returnCode': code, 'observedBy': via,
            'snapshot': self.snapshot()}
        self.emit('worker-accounting-terminal.json')

    def stop_test(self):
        self.finish = self.snapshot()
        self.emit('worker-accounting.json')

    def report(self):
        result = {'profile': 'hms.worker-resource-observation/1', 'testId': self.test_id,
            'testStart': self.start, 'testFinish': self.finish, 'launch': self.launch,
            'errors': list(self.errors), 'testDelta': None, 'launchToReapDelta': None,
            'units': {'ru_utime': 'seconds', 'ru_stime': 'seconds', 'ru_maxrss': 'KiB on Linux',
                'ru_inblock': 'filesystem input operations', 'ru_oublock': 'filesystem output operations',
                'ru_nvcsw': 'voluntary switches', 'ru_nivcsw': 'involuntary switches'},
            'limits': {'pressureScope': 'global host context; no process attribution',
                'childScope': 'terminated and waited-for direct child plus its waited-for descendants',
                'requiresExternalLaunchAndArchiveAudit': True, 'pidBasedSampling': False,
                'peakRssIsNotAdditive': True, 'waitCauseMeasured': False,
                'unmaintainedLinuxFieldsMayBeZero': True, 'physicalEffectsAttested': False}}
        if self.start is not None and self.finish is not None:
            result['testDelta'] = _usage_delta(self.start, self.finish)
        if self.launch is not None and self.launch['terminal'] is not None:
            result['launchToReapDelta'] = _usage_delta(self.launch['before'], self.launch['terminal']['snapshot'])
        return result


def _observed_popen(original, observer):
    class ObservedPopen(original):
        def __init__(self, args, *positional, **keywords):
            observer.before_launch(args)
            try:
                super().__init__(args, *positional, **keywords)
            except BaseException as error:
                observer.failed_launch(error)
                raise
            observer.launched(self)

        def poll(self):
            code = super().poll()
            if code is not None:
                try:
                    observer.observed_return(self, code, 'original-poll')
                except Exception as error:
                    observer.note_error('terminal-poll-observation', error)
            return code

        def wait(self, timeout=None):
            code = super().wait(timeout=timeout)
            try:
                observer.observed_return(self, code, 'original-wait')
            except Exception as error:
                observer.note_error('terminal-wait-observation', error)
            return code
    return ObservedPopen
