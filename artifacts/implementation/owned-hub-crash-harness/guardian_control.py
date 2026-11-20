"""Original finite adoption controls: separate sessions and exact child authority."""
import json
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from guardian import Guardian, read_record, write_record

TERMINATING = False


def terminate(*_):
    global TERMINATING
    if not TERMINATING:
        TERMINATING = True
        raise RuntimeError('guardian control requested to clean up')


def main():
    assert len(sys.argv) == 3
    signal.signal(signal.SIGTERM, terminate)
    root = Path(sys.argv[1]).absolute(); root.mkdir(mode=0o700)
    guardian = Guardian(sys.argv[2]); cases = []
    try:
        for depth in (2, 3):
            notice_r, notice_w = os.pipe2(os.O_CLOEXEC)
            gates = [os.pipe2(os.O_CLOEXEC) for _ in range(depth)]
            def fixed_owner():
                os.close(notice_r)
                for _, writer in gates:
                    os.close(writer)
                chain = []
                for level in range(depth):
                    os.setsid(); chain.append(os.getpid())
                    if level+1 < depth:
                        child = os.fork()
                        if child != 0:
                            for index, (reader, _) in enumerate(gates):
                                if index != level:
                                    os.close(reader)
                            os.close(notice_w)
                            os.read(gates[level][0], 1)
                            os._exit(0)
                    else:
                        for index, (reader, _) in enumerate(gates):
                            if index != level:
                                os.close(reader)
                        write_record(notice_w, dict(chain=chain, lastParent=os.getppid(),
                            subreaper=guardian.helper.hms_subreaper_get()))
                        os.close(notice_w)
                        os.read(gates[level][0], 1)
                        os._exit(0)
            owner = guardian.fork(fixed_owner)
            os.close(notice_w)
            for reader, _ in gates:
                os.close(reader)
            try:
                note = read_record(notice_r)
                chain = note['chain']
                assert len(chain) == depth and chain[0] == owner and note['subreaper'] == 0
                assert note['lastParent'] == chain[-2]
                transitions = []
                for index, pid in enumerate(chain):
                    guardian.refresh()
                    assert pid in guardian.handles
                    observed = guardian.stat(pid)
                    assert observed['parent'] == guardian.pid and observed['group'] == pid and observed['session'] == pid
                    if index+1 < depth:
                        try:
                            guardian.register(chain[index+1])
                        except ChildProcessError:
                            pass
                        else:
                            raise AssertionError('Non-child unexpectedly acquired signal authority')
                        guardian.send(pid, signal.SIGKILL)
                        result = guardian.wait_exit(pid)
                        assert result['exitCode'] == -signal.SIGKILL
                    else:
                        os.close(gates[index][1]); gates[index] = (gates[index][0], None)
                        result = guardian.wait_exit(pid)
                        assert result['exitCode'] == 0
                    transitions.append(result)
                assert guardian.empty()
                cases.append(dict(depth=depth, kernelChildAuthority=True, nonChildRefused=True,
                                  adoptedSeparateSessions=True, records=transitions))
            finally:
                os.close(notice_r)
                for _, writer in gates:
                    if writer is not None:
                        os.close(writer)
                guardian.settle()
        assert guardian.empty()
        result = dict(passed=True, cases=cases, childrenReaped=len(guardian.records),
                      completeForFixedForkTrees=True, universalContainment=False, providerJobsExecuted=False)
        with (root/'checks.json').open('x') as target:
            json.dump(result, target, indent=2, sort_keys=True); target.write('\n')
            target.flush(); os.fsync(target.fileno())
    finally:
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            guardian.settle(); guardian.close()
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    print(json.dumps(dict(passed=True, cases=2, childrenReaped=5, subreaperRestored=True), sort_keys=True))


if __name__ == '__main__':
    main()
