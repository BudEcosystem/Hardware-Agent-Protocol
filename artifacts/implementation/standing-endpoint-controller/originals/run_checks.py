#!/usr/bin/env python3
"""Isolated original-source checks. Never execute an AVR image or access devices.

Source review must precede invocation. Host compilers execute; native probes use
only original in-memory register models. AVR output is compile/link evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import resource
import shutil
import signal
import subprocess
import sys
import tarfile
import time

HERE = Path(__file__).resolve().parent
PROJECT = HERE / 'project'
REPO = HERE.parents[2]
BUILD = None  # Assigned to a new, stage-specific attempt directory in main.
ARCHIVE = REPO / 'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
ARCHIVE_SHA = 'bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
DEFAULT_BIN = Path('/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin')
UNITS = [('protocol/endpoint/endpoint.c','endpoint'),('protocol/endpoint/link.c','link'),
         ('protocol/serial/frame.c','frame'),('tests/endpoint_fixture.c','fixture'),
         ('protocol/platform/avr_uart.c','uart'),('protocol/platform/avr_usart.c','usart'),
         ('protocol/platform/avr_clock.c','clock'),('protocol/platform/avr_eeprom.c','eeprom'),
         ('protocol/platform/boot_epoch.c','boot'),('protocol/platform/avr_runtime.c','runtime')]
COMMON = ['-std=c11','-g','-Wall','-Wextra','-Wconversion','-Werror','-Wvla','-fno-common']
AVR_FLAGS = ['-mmcu=atmega328p','-DF_CPU=16000000UL',*COMMON,'-Os','-ffunction-sections',
             '-fdata-sections','-fno-optimize-sibling-calls','-fstack-usage','-MD']
commands = []

def require(test, message):
    if not test:
        raise RuntimeError(message)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')

def limits(sanitizer):
    resource.setrlimit(resource.RLIMIT_CPU,(30,30))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if not sanitizer:
        resource.setrlimit(resource.RLIMIT_AS,(512*1024**2,512*1024**2))

def group_members(pgid):
    members = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2]) == pgid:
                members.append({'pid':int(entry.name),'state':fields[0],
                                'rss':int(fields[21])*os.sysconf('SC_PAGE_SIZE')})
        except (FileNotFoundError,ProcessLookupError,PermissionError):
            pass
    return members

def child_exited_unreaped(process):
    # WNOWAIT keeps the owned leader PID reserved until group cleanup completes.
    # Popen.poll()/wait() would reap it and permit numeric PGID reuse.
    return os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT) is not None

def finish_owned_group(process):
    pgid=process.pid
    child_exited_unreaped(process)  # Confirm the leader remains our waitable child.
    before=[m for m in group_members(pgid) if m['pid']!=process.pid]
    if not child_exited_unreaped(process) or before:
        try:os.killpg(pgid,signal.SIGKILL)
        except ProcessLookupError:pass
    deadline=time.monotonic()+2
    while [m for m in group_members(pgid) if m['pid']!=process.pid] and time.monotonic()<deadline:
        time.sleep(0.02)
    code=process.wait()  # Reap only after the final group signal; never signal after this.
    return code,before,group_members(pgid)

def run(argv, name, *, sanitizer=False, wall=60):
    """Per-process CPU/AS/file limits plus process-group wall and RSS monitor."""
    out, err = BUILD/(name+'.stdout'), BUILD/(name+'.stderr')
    env = {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1',
           'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
    start=time.monotonic();peak=0;reason=None;code=None;process=None;leftovers=[];remaining=[];monitor_error=None
    with out.open('wb') as stdout,err.open('wb') as stderr:
        process=subprocess.Popen([str(a) for a in argv],cwd=PROJECT,env=env,stdin=subprocess.DEVNULL,
            stdout=stdout,stderr=stderr,start_new_session=True,preexec_fn=lambda:limits(sanitizer))
        try:
            while not child_exited_unreaped(process):
                peak=max(peak,sum(member['rss'] for member in group_members(process.pid)))
                if time.monotonic()-start>wall:reason='wall_limit'
                if peak>512*1024**2:reason='resident_group_limit'
                if reason:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    break
                time.sleep(0.02)
        except BaseException as exc:
            monitor_error=exc;reason='monitor_exception: '+str(exc)
        finally:
            code,leftovers,remaining=finish_owned_group(process)
    record={'argv':[str(a) for a in argv],'exit_code':code,'seconds':time.monotonic()-start,
            'max_observed_process_group_rss_bytes':peak,'monitor_interval_ms':20,'termination_reason':reason,
            'pid':process.pid,'pgid':process.pid,'direct_child_reaped':True,
            'group_signal_anchor':'waitable unreaped owned leader; no signals after wait()',
            'leftover_members_after_direct_child':leftovers,'group_members_after_cleanup':remaining,
            'stdout':str(out.relative_to(HERE)),'stderr':str(err.relative_to(HERE)),
            'limits':{'wall_seconds':wall,'cpu_seconds_per_process':30,'file_bytes':64*1024**2,
                      'open_files':64,'virtual_bytes':None if sanitizer else 512*1024**2,
                      'resident_group_bytes':512*1024**2,'core_bytes':0}}
    commands.append(record);write_json(BUILD/'commands.json',commands)
    if monitor_error is not None:raise monitor_error
    require(not remaining,f'{name}: process group not absent after cleanup')
    require(code==0 and reason is None,f'{name} failed; see {err}')
    require(not err.stat().st_size,f'{name} wrote diagnostics; see {err}')
    return out.read_text()

def native():
    gcc=Path(shutil.which('gcc') or '').resolve();require(gcc.is_file(),'Native GCC missing')
    # This is the unchanged original suite/pipe-smoke runner in the copied tree.
    # ASan reserves a large virtual shadow; RSS/wall/CPU/file bounds still apply.
    original=json.loads(run([sys.executable,'scripts/check_endpoint_native.py'],'original-native',sanitizer=True))
    inputs=[path for path,_ in UNITS]+['tests/reference_link.c','tests/avr_runtime_probe.c']
    macros=['-DHMS_AVR_UART_TEST','-DHMS_AVR_USART_TEST','-DHMS_AVR_CLOCK_TEST','-DHMS_AVR_EEPROM_TEST']
    reports={}
    for mode in ('plain','asan'):
        flags=['-O2'] if mode=='plain' else ['-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie']
        exe=BUILD/('runtime-'+mode)
        run([gcc,*COMMON,*flags,*macros,*inputs,'-o',exe],'compile-'+mode)
        reports[mode]=json.loads(run([exe],'probe-'+mode,sanitizer=mode=='asan'))
        require(reports[mode]['cases']==11 and reports[mode]['wireOracleSteps']==20000,'Probe coverage changed')
    return {'original':original,'integration':reports,'compiler_path':str(gcc),'compiler_sha256':digest(gcc)}

def pinned_tools(binary):
    require(digest(ARCHIVE)==ARCHIVE_SHA,'Approved compiler archive differs')
    hashes,links={},{}
    with tarfile.open(ARCHIVE,'r|bz2') as archive:
        for member in archive:
            if member.isfile():
                hashes[member.name]=hashlib.file_digest(archive.extractfile(member),'sha256').hexdigest()
            elif member.islnk():links[member.name]=member.linkname
            elif member.issym():links[member.name]=posixpath.normpath(posixpath.join(posixpath.dirname(member.name),member.linkname))
    for _ in range(len(links)):
        resolved={name:hashes[target] for name,target in links.items() if target in hashes}
        if not resolved:break
        hashes.update(resolved)
        for name in resolved:del links[name]
    toolroot=binary.resolve().parent;pins={}
    def pin(path):
        path=Path(path).resolve();require(path.is_relative_to(toolroot),f'Outside compiler tree: {path}')
        member='avr/'+str(path.relative_to(toolroot))
        require(digest(path)==hashes.get(member),f'Compiler tree drift: {path}')
        pins[str(path)]={'member':member,'sha256':digest(path),'bytes':path.stat().st_size}
        return path
    tools={name:pin(toolroot/'bin'/('avr-'+name)) for name in ('gcc','as','ld','size','nm','objdump')}
    for name in ('cc1','collect2'):pin(toolroot/'libexec/gcc/avr/7.3.0'/name)
    # Pin every header/library/spec before the compiler can consume it.
    for directory in (toolroot/'avr/include',toolroot/'avr/lib',toolroot/'lib/gcc/avr/7.3.0'):
        for path in directory.rglob('*'):
            if path.is_file():pin(path)
    return tools,pin,pins

def avr(binary):
    tools,pin,pins=pinned_tools(binary);gcc=tools['gcc'];objects=[];records=[]
    version=run([gcc,'--version'],'avr-version').splitlines()[0]
    require(run([gcc,'-dumpmachine'],'avr-machine').strip()=='avr','Wrong compiler target')
    for name in ('as','ld','cc1','collect2'):
        pin(run([gcc,'-print-prog-name='+name],'avr-program-'+name).strip())
    for source,unit in UNITS+[('tests/avr_runtime_target.c','target')]:
        obj=BUILD/(unit+'.o');run([gcc,*AVR_FLAGS,'-c',source,'-o',obj],'avr-compile-'+unit);objects.append(obj)
        for line in obj.with_suffix('.su').read_text().splitlines():
            location,count,qualification=line.split('\t')
            require(qualification in ('static','dynamic,bounded'),'Unbounded compiler stack record')
            records.append({'unit':unit,'location':location,'function':location.split(':',3)[3],
                            'bytes':int(count),'qualification':qualification})
    elf=BUILD/'runtime.elf';map_path=BUILD/'runtime.map'
    run([gcc,'-mmcu=atmega328p','-Os','-Wl,--gc-sections',
         '-Wl,--undefined=hms_endpoint_link_feed','-Wl,--undefined=hms_avr_uart_frame_step',
         '-Wl,--undefined=hms_avr_usart_drained','-Wl,--defsym=__TEXT_REGION_LENGTH__=32768',
         '-Wl,--defsym=__DATA_REGION_LENGTH__=2048','-Wl,--defsym=__DATA_REGION_ORIGIN__=0x800100',
         '-Wl,--defsym=__EEPROM_REGION_LENGTH__=1024','-Wl,-Map='+str(map_path),*objects,'-o',elf],'avr-link')
    sections_text=run([tools['size'],'-A',elf],'avr-sections')
    symbols_text=run([tools['nm'],'-S','--size-sort',elf],'avr-symbols')
    run([tools['objdump'],'-h','-d',elf],'avr-disassembly')
    require(not run([tools['nm'],'-u',elf],'avr-undefined').strip(),'Unresolved symbols')
    for match in re.finditer(r'^LOAD (\S+)',map_path.read_text(),re.M):
        path=Path(match.group(1))
        if path.is_absolute() and not path.is_relative_to(BUILD):pin(path)
    sections={}
    for line in sections_text.splitlines():
        fields=line.split()
        if len(fields)==3 and fields[0].startswith('.'):sections[fields[0]]=int(fields[1])
    allocations={};symbols=[]
    for line in symbols_text.splitlines():
        fields=line.split()
        if len(fields)==4:
            address,size,kind,name=fields;symbols.append({'address':int(address,16),'bytes':int(size,16),'type':kind,'name':name})
            if kind in 'BbDd':allocations[name]=int(size,16)
    require(not ({s['name'] for s in symbols}&{'malloc','calloc','realloc','free','alloca'}),'Allocator linked')
    require(allocations['hms_target_fixture']+allocations['hms_target_primitive_reserve']==256,'Primitive reservation changed')
    require(allocations['hms_target_protection_reserve']==64,'Protection reservation changed')
    require({'__vector_13','__vector_18'}<={s['name'] for s in symbols},'Timer1/USART RX vector missing')
    write_json(BUILD/'stack-records.json',records);write_json(BUILD/'symbols.json',symbols)
    flash=sections.get('.text',0)+sections.get('.data',0)
    static=sum(sections.get(name,0) for name in ('.data','.bss','.noinit'))
    return {'compiler_version':version,'toolchain_pins':pins,'mcu':'atmega328p','declared_f_cpu_hz':16000000,
            'flags':AVR_FLAGS,'flash_bytes':flash,'static_sram_bytes':static,'sections':sections,'allocations':allocations,
            'limits':{'physical_flash':32768,'uno_application_flash':32256,'sram':2048,'eeprom':1024},
            'static_plus_512_stack_bytes':static+512,'static_reservation_arithmetic_fits':flash<=32256 and static+512<=2048,
            'combined_foreground_isr_stack_analysis':'PENDING: old no-ISR fixture bound is inapplicable',
            'tx_register_instruction_window_review':'PENDING: inspect exact linked sequence and max baud interval',
            'target_runtime_fit_demonstrated':False,'target_executed':False}

def main():
    global BUILD,PROJECT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=('native','avr'))
    parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--toolchain-bin',type=Path,default=DEFAULT_BIN);opts=parser.parse_args()
    def interrupted(signum, _frame):
        raise RuntimeError('Runner interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted)
    require(opts.attempt>0,'Attempt must be positive')
    suffix='' if opts.attempt==1 else '-attempt-'+str(opts.attempt)
    BUILD=HERE/'build'/(opts.stage+suffix)
    destination=HERE/('checks-'+opts.stage+suffix+'.json')
    require(not destination.exists() and not BUILD.exists(),'Attempt already exists; preserve it and select a new explicit --attempt')
    BUILD.mkdir(parents=True,exist_ok=False)
    sources={str(p.relative_to(HERE)):digest(p) for p in sorted(PROJECT.rglob('*'))
             if p.is_file() and 'artifacts' not in p.relative_to(PROJECT).parts and '__pycache__' not in p.parts}
    sources['run_checks.py']=digest(Path(__file__))
    for name,value in sources.items():
        destination_source=BUILD/name;destination_source.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(HERE/name,destination_source)
        require(digest(destination_source)==value,'Source changed while preparing private byte copy')
    PROJECT=BUILD/'project'
    report={'schema':'hms-avr-link-integration/1','recorded_at':datetime.now(timezone.utc).isoformat(),
            'sources':sources,'stage':opts.stage,'attempt':opts.attempt,'public_edits':False,'target_executed':False,
            'requested_checks_completed':False,
            'source_snapshot_basis':'Per-attempt private source byte copies prepared and verified before execution; no filesystem immutability claim',
            'frozen_source_copy_root':str(BUILD.relative_to(HERE))}
    write_json(destination,report)
    try:
        if opts.stage=='native':report['native']=native()
        if opts.stage=='avr':report['avr']=avr(opts.toolchain_bin)
        require(all(digest(HERE/name)==value for name,value in sources.items()),'Source changed during check')
        report['requested_checks_completed']=True
    except BaseException as exc:
        report['requested_checks_completed']=False;report['error']=str(exc);raise
    finally:
        report['source_hashes_after']={name:digest(HERE/name) if (HERE/name).is_file() else None for name in sources}
        report['sources_unchanged']=report['source_hashes_after']==sources
        report['copied_source_hashes_after']={name:digest(BUILD/name) if (BUILD/name).is_file() else None for name in sources}
        report['copied_sources_unchanged']=report['copied_source_hashes_after']==sources
        report['final_group_audit']=[{'pgid':c['pgid'],'members':group_members(c['pgid'])} for c in commands]
        report['owned_groups_absent']=all(not audit['members'] for audit in report['final_group_audit'])
        if not report['sources_unchanged'] or not report['copied_sources_unchanged'] or not report['owned_groups_absent']:
            report['requested_checks_completed']=False
        report['commands']=commands;write_json(destination,report)
    require(report['requested_checks_completed'],'Final audit failed')
    print(json.dumps({'receipt':str(destination),'requested_checks_completed':True,
                      'target_executed':False,'runtime_fit_claimed':False}))

if __name__=='__main__':main()
