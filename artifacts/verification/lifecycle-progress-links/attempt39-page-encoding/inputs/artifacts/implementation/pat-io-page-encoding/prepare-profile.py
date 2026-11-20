"""Profile the terminal GPIO deadline failure without changing source or limits."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path.cwd(); B = ROOT / 'artifacts/implementation/pat-io-page-encoding'
O = B / 'harness03'; H = B / 'harness05'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_bytes())
def write(p, v):
    with p.open('x') as f: f.write(json.dumps(v, indent=2) + '\n')
assert read(B / 'results/attempt03-failed-gpio-history/attempt/result.json')['childState'] == 'exited'
assert sha(O / 'index.json') == '71ab75814eeb2b93cf91332e6346eca977775af80c88dbab2922058789b6d5ce'
for row in read(O / 'index.json')['files']: assert sha(O / row['path']) == row['sha256']
H.mkdir(); (H / 'references').mkdir()
borrowed = []
for name in ('run_attempt.py', 'attempt_child.py', 'references/approved-external-roots.json'):
    p = O / name; q = H / 'references' / p.name; shutil.copyfile(p, q)
    borrowed.append(dict(source=p.relative_to(ROOT).as_posix(), copy=q.relative_to(H).as_posix(), bytes=p.stat().st_size, sha256=sha(p)))
write(H / 'borrowed-inputs.json', borrowed)
for name in ('run_attempt.py', 'targets.json', 'SCOPE.md'): shutil.copyfile(O / name, H / name)
before = (O / 'attempt_child.py').read_text()
anchor = '    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(tests)\n'
replacement = '''    import cProfile
    import time
    profiler = cProfile.Profile()
    profile_wall, profile_cpu = time.monotonic(), time.process_time()
    profiler.enable()
    try:
        result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(tests)
    finally:
        profiler.disable()
        wall_seconds, cpu_seconds = time.monotonic() - profile_wall, time.process_time() - profile_cpu
        profile_rows = []
        for entry in profiler.getstats():
            code = entry.code
            label = code if isinstance(code, str) else code.co_filename + ':' + str(code.co_firstlineno) + ':' + code.co_name
            profile_rows.append(dict(label=label, calls=entry.callcount, recursiveCalls=entry.reccallcount,
                                     cumulativeSeconds=entry.totaltime, selfSeconds=entry.inlinetime))
        profile_rows.sort(key=lambda row: (-row['cumulativeSeconds'], row['label']))
        write('profile.json', dict(scope='Instrumented exact full GPIO history target after imports; incomplete capture remains failed. Timings include profiler overhead.',
            wallSeconds=wall_seconds, cpuSeconds=cpu_seconds, totalFunctions=len(profile_rows),
            top100=profile_rows[:100], top100Self=sorted(profile_rows, key=lambda row: (-row['selfSeconds'], row['label']))[:100]))
'''
assert before.count(anchor) == 1
after = before.replace(anchor, replacement); ast.parse(after)
(H / 'attempt_child.py').write_text(after)
(H / 'attempt_child.py.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
    fromfile=(O / 'attempt_child.py').relative_to(ROOT).as_posix(), tofile=(H / 'attempt_child.py').relative_to(ROOT).as_posix())))
(H / 'README.md').write_text('# Current GPIO diagnostic profile\n\nThe same [target](targets.json), [source](../implementation01/README.md) and\n[scope](SCOPE.md) apply. Instrumentation adds overhead; this is not a benchmark\nor a replacement for the retained uninstrumented failure.\n')
review = read(O / 'review.json')
review.update(scope='Primary-agent complete profiling wrapper reviewed before execution.')
review['reviewed'] += ['Original launcher, selection, source and all capture/harness limits unchanged. cProfile wraps the single full GPIO method after imports. Top100 cumulative/self rows and process/wall totals are bounded JSON, no binary dump. Timing overhead does not qualify performance or turn an incomplete capture into success. Original failed attempt remains retained.']
write(H / 'review.json', review)
rows = [dict(path=p.relative_to(H).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(H.rglob('*')) if p.is_file()]
write(H / 'index.json', dict(scope='Frozen bounded diagnostic around unchanged full GPIO history target.', files=rows))
print(json.dumps(dict(harness=H.name, indexSha256=sha(H / 'index.json'))))
