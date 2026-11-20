#!/usr/bin/env python3
"""Independent host-only checks of frozen AVR clock source; never executes AVR."""
from datetime import datetime, timezone
import hashlib, json, os
from pathlib import Path
import shutil, subprocess, sys

ROOT=Path(__file__).resolve().parents[3]
BASE=Path(__file__).resolve().parent
INPUTS=json.loads((BASE/'input-snapshots.json').read_text())
SNAP=BASE/'snapshots'
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(ok,message):
    if not ok: raise RuntimeError(message)
def record(path):
    return dict(path=str(path.relative_to(ROOT)),sha256=digest(path),bytes=path.stat().st_size)
def frozen():
    for row in INPUTS['files']:
        require(digest(ROOT/row['snapshot_path'])==row['sha256'],'Snapshot changed: '+row['snapshot_path'])
        require(digest(ROOT/row['original_path'])==row['sha256'],'Frozen source/output changed: '+row['original_path'])
frozen()
producer=json.loads((SNAP/'artifacts/verification/avr-clock/review.json').read_text())
require(producer['passed'] and producer['avr']['executed'] is False,'Unexpected producer scope')
compiler=Path(shutil.which('gcc')).resolve()
require(str(compiler)==producer['host_compiler']['path'] and digest(compiler)==producer['host_compiler']['sha256'], 'Host compiler differs from producer pin')
environment={k:v for k,v in os.environ.items() if k not in {
    'GCC_EXEC_PREFIX','COMPILER_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH',
    'LIBRARY_PATH','LD_PRELOAD','LD_LIBRARY_PATH','LD_AUDIT','DEPENDENCIES_OUTPUT','SUNPRO_DEPENDENCIES'}}
environment.update(LC_ALL='C',ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
commands=[]
def run(argv,expected=0):
    result=subprocess.run([str(x) for x in argv],cwd=ROOT,env=environment,capture_output=True,text=True,timeout=60)
    commands.append(dict(argv=[str(x) for x in argv],exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr))
    (BASE/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
    require(result.returncode==expected,f'Unexpected exit {result.returncode} wanted {expected}: {argv}\n{result.stdout}\n{result.stderr}')
    return result
common=['-std=c11','-Wall','-Wextra','-Wconversion','-Werror','-Wvla','-fno-common','-DHMS_AVR_CLOCK_TEST',
        '-I',SNAP/'protocol/platform']
original=SNAP/'protocol/platform/avr_clock.c'
probe=BASE/'independent_probe.c'
baselines=[]
for name,flags in [('optimized',['-O2']),('asan-ubsan',['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie'])]:
    binary=BASE/'build'/name
    run([compiler,*common,*flags,original,probe,'-o',binary])
    result=json.loads(run([binary]).stdout)
    require(result['passed'] and not result['target_executed'] and not result['instruction_emulation'],'Bad probe scope')
    require(result['timeline_cases']==131920 and result['conversion_cases']==8192056 and result['sequence_steps']==100000 and result['outside_contract_aliases']==5,'Unexpected independent campaign coverage')
    baselines.append(dict(variant=name,result=result,binary=record(binary)))
text=original.read_text()
mutations=[
 ('omit_pending_compensation','else ++high; /* Pending compensation; flag/high word untouched. */','else high += 0u; /* Intentionally broken: pending wrap omitted. */'),
 ('omit_wrap_reread','if (!before) low = counter(); /* Crossed wrap during first sample. */','if (!before) { /* Intentionally broken: old low retained. */ }'),
 ('read_high_before_low','uint8_t low = READ(R_LOW); /* Latches high byte in shared TEMP. */\n    uint8_t high = READ(R_HIGH);','uint8_t high = READ(R_HIGH);\n    uint8_t low = READ(R_LOW);'),
 ('relax_late_read_boundary','if (low >= HMS_AVR_CLOCK_SERVICE_LIMIT)','if (low > HMS_AVR_CLOCK_SERVICE_LIMIT)'),
 ('relax_late_isr_boundary','else if (counter() >= HMS_AVR_CLOCK_SERVICE_LIMIT','else if (counter() > HMS_AVR_CLOCK_SERVICE_LIMIT'),
 ('lose_sticky_qualification','if (!clock->fault) clock->qualified = 1;','clock->fault = 0; clock->qualified = 1;'),
 ('remove_epoch_check','!clock->started || boot_epoch != clock->boot_epoch || assurances != HMS_AVR_CLOCK_ALL_ASSURED','!clock->started || (boot_epoch == 0u) || assurances != HMS_AVR_CLOCK_ALL_ASSURED'),
 ('wrong_ms_divisor','residual / HMS_AVR_CLOCK_RAW_PER_MS','residual / 249u'),
 ('remove_exhaustion_guard','else if (high == UINT32_MAX) fault(clock, HMS_AVR_CLOCK_EXHAUSTED);','else if (high == UINT32_MAX && low == UINT16_MAX) fault(clock, HMS_AVR_CLOCK_EXHAUSTED);'),
 ('remove_regression_guard','fault(clock, HMS_AVR_CLOCK_REGRESSION);','clock->have_last = 0; /* Intentionally broken: forget regression. */'),
 ('wrong_saved_interrupt_state','restore(saved);','restore((uint8_t)(saved | 0x80u));'),
 ('consume_pending_flag','else ++high; /* Pending compensation; flag/high word untouched. */','else { ++high; WRITE(R_FLAG, 1u); }'),
]
mutant_results=[]
for name,old,new in mutations:
    require(old in text,'Mutation no longer matches '+name)
    mutated=text.replace(old,new) if name=='wrong_saved_interrupt_state' else text.replace(old,new,1)
    source=BASE/'mutations'/(name+'.c'); source.write_text(mutated)
    binary=BASE/'build'/('mutant-'+name)
    run([compiler,*common,'-O2',source,probe,'-o',binary])
    failed=run([binary,'quick'],expected=11)
    mutant_results.append(dict(name=name,source=record(source),binary=record(binary),rejected=True,exit_code=failed.returncode,diagnostic=failed.stderr.strip()))
frozen()
report=dict(schema='hms-avr-clock-independent-review/1',created_at=datetime.now(timezone.utc).isoformat(),passed=True,
    source_freeze_verified=True,producer_receipt_sha256=INPUTS['producer_receipt_sha256'],
    source_snapshots=len(INPUTS['files']),host_compiler=producer['host_compiler'],
    baselines=baselines,source_mutations=mutant_results,source_mutations_rejected=len(mutant_results),
    inputs=[record(BASE/'input-snapshots.json'),record(probe),record(Path(__file__))],
    command_log=record(BASE/'commands.json'),
    target_executed=False,emulator_executed=False,hardware_contacted=False,acquired_research_code_executed=False,
    scope='Independent host-native register/history model and source mutants. No AVR instruction execution, cycles, timing, oscillator, deployment qualification or combined firmware fit claim.')
(BASE/'results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(passed=True,baselines=baselines,source_mutations_rejected=len(mutant_results),results_sha256=digest(BASE/'results.json')),indent=2))
