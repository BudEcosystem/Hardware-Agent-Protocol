#!/usr/bin/env python3
"""Isolated original-source checks. Never execute an AVR image or access devices.

Source review must precede invocation. Host compilers execute; native probes use
only original in-memory register models. AVR output is compile/link evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
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
import threading

HERE = Path(__file__).resolve().parent
PROJECT = HERE / 'project'
REPO = HERE.parents[2]
BUILD = None  # Assigned to a new, stage-specific attempt directory in main.
ARCHIVE = REPO / 'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
ARCHIVE_SHA = 'bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
DEFAULT_BIN = Path('/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin')
UNITS = [('protocol/endpoint/endpoint.c','endpoint'),('protocol/endpoint/link.c','link'),
         ('protocol/endpoint/standing.c','standing'),
         ('protocol/serial/frame.c','frame'),('tests/endpoint_fixture.c','fixture'),
         ('protocol/platform/avr_uart.c','uart'),('protocol/platform/avr_usart.c','usart'),
         ('protocol/platform/avr_clock.c','clock'),('protocol/platform/avr_eeprom.c','eeprom'),
         ('protocol/platform/boot_epoch.c','boot'),('protocol/platform/avr_runtime.c','runtime')]
COMMON = ['-std=c11','-g','-Wall','-Wextra','-Wconversion','-Werror','-Wvla','-fno-common']
AVR_FLAGS = ['-mmcu=atmega328p','-DF_CPU=16000000UL',*COMMON,'-Os','-ffunction-sections',
             '-fdata-sections','-fno-optimize-sibling-calls','-fstack-usage','-MD']
commands = []
BLOCKED = {signal.SIGINT, signal.SIGTERM}
ENVIRONMENT = {'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','PYTHONDONTWRITEBYTECODE':'1',
               'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1',
               'UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
SOURCE_PINS = {}
INSTALLED_PINS = {}
CRITICAL_PINS = set()
OWNER = None
RUNTIME_FD = None
RUNTIME_SHA = None
FINAL_DESTINATION = None
FINAL_REPORT = None
PROCESS_OBJECTS = []  # Keep Popen destructors from becoming competing reapers.

def require(test, message):
    if not test:
        raise RuntimeError(message)

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def write_json(path, value):
    # Aggregate summaries may advance; immutable per-command phase receipts
    # below retain every launch intent/start/result independently.
    temporary=path.with_name(path.name+'.new')
    require(not temporary.exists(),'Unsettled receipt temporary already exists: '+str(temporary))
    with temporary.open('x') as target:
        json.dump(value,target,indent=2,sort_keys=True);target.write('\n')
        target.flush();os.fsync(target.fileno())
    os.replace(temporary,path)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:os.fsync(directory)
    finally:os.close(directory)

def save_new(path,value):
    with path.open('x') as target:
        json.dump(value,target,indent=2,sort_keys=True);target.write('\n')
        target.flush();os.fsync(target.fileno())
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:os.fsync(directory)
    finally:os.close(directory)

def fd_digest(fd):
    value=hashlib.sha256();offset=0
    while True:
        block=os.pread(fd,1024*1024,offset)
        if not block:return value.hexdigest()
        value.update(block);offset+=len(block)

def observed_hash(path):
    try:return digest(Path(path))
    except (OSError,ValueError) as error:return {'error':type(error).__name__+': '+str(error)}

def input_snapshot():
    return {'original':{name:observed_hash(HERE/name) for name in SOURCE_PINS},
            'frozen':{name:observed_hash(BUILD/name) for name in SOURCE_PINS}}

def input_stable(snapshot):
    return snapshot['original']==SOURCE_PINS and snapshot['frozen']==SOURCE_PINS

def installed_expected(critical_only=False):
    return {name:value for name,value in INSTALLED_PINS.items()
            if not critical_only or name in CRITICAL_PINS}

def installed_snapshot(critical_only=False):
    return {name:observed_hash(name) for name in installed_expected(critical_only)}

def runtime_snapshot():
    try:opened=fd_digest(RUNTIME_FD) if RUNTIME_FD is not None else None
    except OSError as error:opened={'error':type(error).__name__+': '+str(error)}
    return {'running':observed_hash('/proc/self/exe'),
            'selected':observed_hash(Path(sys.executable).resolve()),
            'opened':opened}

def runtime_stable(snapshot):
    return all(value==RUNTIME_SHA for value in snapshot.values())

def pin_installed(path,expected=None,*,critical=True):
    path=Path(path).resolve();value=digest(path)
    if expected is not None:require(value==expected,'Installed file differs: '+str(path))
    if str(path) in INSTALLED_PINS:require(INSTALLED_PINS[str(path)]==value,'Installed file changed: '+str(path))
    INSTALLED_PINS[str(path)]=value
    if critical:CRITICAL_PINS.add(str(path))
    return path

def owner_precondition():
    require(OWNER is not None,'Dedicated owner is not initialized')
    OWNER.guard()
    require(len(os.listdir('/proc/self/task'))==1 and threading.get_native_id()==os.getpid(),
            'Runner must remain its sole native thread')

def pending_interrupts():
    return sorted(int(value) for value in signal.sigpending()&BLOCKED)

def limits(sanitizer,previous_mask):
    # Parent blocks INT/TERM around ownership capture; the child must not carry
    # those blocks into the compiler/test. This preexec hook requires one thread.
    signal.signal(signal.SIGINT,signal.SIG_DFL)
    signal.signal(signal.SIGTERM,signal.SIG_DFL)
    signal.pthread_sigmask(signal.SIG_SETMASK,previous_mask)
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
        except (FileNotFoundError,ProcessLookupError):
            pass
        except (PermissionError,ValueError,IndexError) as error:
            raise RuntimeError('Process-group observation is incomplete') from error
    return members

def child_exited_unreaped(process):
    # WNOWAIT keeps the owned leader PID reserved until group cleanup completes.
    # Popen.poll()/wait() would reap it and permit numeric PGID reuse.
    owner_precondition()
    require(process.returncode is None,'Leader was already reaped')
    result=OWNER.status(process.pid)
    require(os.getpgid(process.pid)==process.pid and os.getsid(process.pid)==process.pid,
            'Owned leader changed process group/session')
    return result is not None

def finish_owned_group(process):
    """All group signals precede leader reap; adopted children use pidfds only."""
    pgid=process.pid
    if pgid not in OWNER.handles:OWNER.register(pgid)
    child_exited_unreaped(process)  # Confirm the leader remains our waitable child.
    before=[m for m in group_members(pgid) if m['pid']!=process.pid]
    if not child_exited_unreaped(process) or before:
        try:os.killpg(pgid,signal.SIGKILL)
        except ProcessLookupError:pass
    deadline=time.monotonic()+3
    while True:
        OWNER.refresh()
        for pid in list(OWNER.handles):
            if pid==pgid:continue
            # Kernel child relation plus retained pidfd, never a stored PID or
            # a signal to this PGID after its leader has been reaped.
            OWNER.send(pid,signal.SIGKILL)
            if OWNER.status(pid) is not None:OWNER.reap(pid)
        members=group_members(pgid)
        if child_exited_unreaped(process) and not [m for m in members if m['pid']!=pgid] and len(OWNER.handles)==1:
            result=OWNER.reap(pgid);process.returncode=result['exitCode']
            return result,before,group_members(pgid)
        require(time.monotonic()<deadline,'Owned group not settled within cleanup bound')
        time.sleep(0.01)

def run(argv, name, *, sanitizer=False, wall=60):
    """One reviewed command in a dedicated, live, nonconcurrent subreaper owner.

    Group RSS is a20ms observation of this PGID, not universal containment or a
    cgroup quota. Compiler descendants may be adopted/reaped during cleanup.
    SIGKILL/host death of this runner is outside its orderly cleanup claim.
    """
    require(re.fullmatch(r'[a-z0-9-]+',name) is not None,'Invalid command receipt name')
    owner_precondition();require(OWNER.empty(),'An earlier command retains children')
    out, err = BUILD/(name+'.stdout'), BUILD/(name+'.stderr')
    intent=BUILD/(name+'.intent.json');started_receipt=BUILD/(name+'.started.json');result_path=BUILD/(name+'.result.json')
    require(not any(p.exists() for p in (out,err,intent,started_receipt,result_path)),
            'Command attempt already exists: '+name)
    start=time.monotonic();peak=0;reason=None;process=None;exit_record=None
    stdout=stderr=None;executable_fd=None;executable=None;executable_before=None
    leftovers=[];remaining=[];caught=None;cleanup_errors=[];launch_attempted=False
    first_reap=len(OWNER.records);before_inputs=input_snapshot();before_runtime=runtime_snapshot()
    before_tools=installed_snapshot(critical_only=True)
    record={'name':name,'argv':[str(a) for a in argv],
        'stdout':str(out.relative_to(HERE)),'stderr':str(err.relative_to(HERE)),
        'inputs_before':before_inputs,'runtime_before':before_runtime,
        'installed_files_before':before_tools,'monitor_interval_ms':20,
        'limits':{'wall_seconds':wall,'cpu_seconds_per_process':30,'file_bytes':64*1024**2,
                  'open_files':64,'virtual_bytes':None if sanitizer else 512*1024**2,
                  'resident_group_observation_bytes':512*1024**2,'core_bytes':0,
                  'anchored_cleanup_seconds':3,'adopted_cleanup_seconds':8},
        'scope':'Live dedicated owner; trusted fixed commands; PGID RSS observations, not universal containment; owner SIGKILL not qualified'}
    try:
        executable=Path(argv[0]).resolve()
        executable_fd=os.open(executable,os.O_RDONLY|os.O_CLOEXEC)
        executable_before=fd_digest(executable_fd)
        require(digest(executable)==executable_before,'Executable changed while opening')
        require(executable.is_relative_to(BUILD) or INSTALLED_PINS.get(str(executable))==executable_before,
                'Executable is not a selected pinned tool or private build output')
        record['executable']={'path':str(executable),'sha256':executable_before,
                              'exec_source':'opened read-only FD through /proc/self/fd; argv0 retains selected path'}
        record['prelaunch_inputs_valid']=input_stable(before_inputs) and runtime_stable(before_runtime) and before_tools==installed_expected(critical_only=True)
        save_new(intent,record)
        require(record['prelaunch_inputs_valid'],'Prelaunch source/tool/runtime pins changed')
        stdout=out.open('xb');stderr=err.open('xb')
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,BLOCKED)
        try:
            owner_precondition();require(not pending_interrupts(),'Interrupt pending before launch')
            launch_attempted=True
            process=subprocess.Popen([str(a) for a in argv],executable='/proc/self/fd/'+str(executable_fd),
                cwd=PROJECT,env=ENVIRONMENT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                start_new_session=True,close_fds=True,pass_fds=(executable_fd,),
                preexec_fn=lambda:limits(sanitizer,previous))
            PROCESS_OBJECTS.append(process)
            OWNER.register(process.pid)
            save_new(started_receipt,{'pid':process.pid,'pgid':process.pid,
                'identity':OWNER.handles[process.pid]['identity'],'started_after_intent':str(intent.relative_to(HERE)),
                'interrupts_pending':pending_interrupts()})
        finally:
            # Any delivered interrupt is caught by the enclosing try, after
            # ownership capture and started receipt have completed.
            signal.pthread_sigmask(signal.SIG_SETMASK,previous)
        while not child_exited_unreaped(process):
            peak=max(peak,sum(member['rss'] for member in group_members(process.pid)))
            if time.monotonic()-start>wall:reason='wall_limit'
            if peak>512*1024**2:reason='resident_group_observation_limit'
            if reason:break
            time.sleep(0.02)
    except BaseException as exc:
        caught=exc;reason=type(exc).__name__+': '+str(exc)
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,BLOCKED)
        try:
            try:
                if process is not None:exit_record,leftovers,remaining=finish_owned_group(process)
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__+': '+str(exc))
            try:
                # Also covers an exceptional Popen/registration return: the
                # dedicated owner began empty, so all adopted children belong
                # to this one command. No process is selected by stale PID.
                OWNER.settle(seconds=8)
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__+': '+str(exc))
            reaped=OWNER.records[first_reap:]
            if process is not None:
                matches=[r for r in reaped if r['pid']==process.pid]
                if matches:exit_record=matches[0];process.returncode=exit_record['exitCode']
                try:remaining=group_members(process.pid)  # Audit only; never signal this PGID now.
                except BaseException as exc:
                    cleanup_errors.append(type(exc).__name__+': '+str(exc));remaining=[{'observation_unknown':True}]
            for stream in (stdout,stderr):
                if stream is not None:
                    try:stream.flush();os.fsync(stream.fileno());stream.close()
                    except BaseException as exc:cleanup_errors.append(type(exc).__name__+': '+str(exc))
            after_inputs=input_snapshot();after_runtime=runtime_snapshot();after_tools=installed_snapshot(critical_only=True)
            try:opened_after=fd_digest(executable_fd) if executable_fd is not None else None
            except OSError as exc:opened_after={'error':type(exc).__name__+': '+str(exc)}
            executable_after={'path':observed_hash(executable) if executable is not None else None,'opened':opened_after}
            if executable_fd is not None:
                try:os.close(executable_fd)
                except OSError as exc:cleanup_errors.append(type(exc).__name__+': '+str(exc))
            pending=pending_interrupts()
            stable=input_stable(after_inputs) and runtime_stable(after_runtime) and after_tools==installed_expected(critical_only=True)
            stable=stable and executable_after=={'path':executable_before,'opened':executable_before}
            record.update(exit_code=exit_record['exitCode'] if exit_record else None,seconds=time.monotonic()-start,
                max_observed_process_group_rss_bytes=peak,termination_reason=reason,
                launch_attempted=launch_attempted,pid=process.pid if process else None,
                pgid=process.pid if process else None,direct_child_reaped=exit_record is not None,
                group_signal_anchor='live kernel-child relation plus retained unreaped leader; no group signal after reap',
                leftover_members_before_cleanup=leftovers,group_members_after_cleanup=remaining,
                owned_children_reaped=reaped,cleanup_errors=cleanup_errors,inputs_after=after_inputs,
                runtime_after=after_runtime,installed_files_after=after_tools,executable_after=executable_after,
                input_pins_stable=stable,interrupts_pending_after_cleanup=pending,
                stdout_sha256=observed_hash(out),stderr_sha256=observed_hash(err))
            try:empty=OWNER.empty()
            except BaseException as exc:
                cleanup_errors.append(type(exc).__name__+': '+str(exc));empty=False
            record['passed']=(reason is None and not cleanup_errors and exit_record is not None and
                exit_record['exitCode']==0 and stable and not pending and not remaining and
                err.is_file() and err.stat().st_size==0 and empty)
            commands.append(record);save_new(result_path,record);write_json(BUILD/'commands.json',commands)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    if caught is not None:raise caught
    require(record['passed'],name+' failed; retained '+str(result_path))
    return out.read_text()

def native():
    gcc=Path(shutil.which('gcc',path=ENVIRONMENT['PATH']) or '').resolve();require(gcc.is_file(),'Native GCC missing')
    pin_installed(gcc)
    native_tools={'gcc':str(gcc)}
    version=run([gcc,'--version'],'native-version').splitlines()[0]
    for name in ('cc1','as','ld','collect2'):
        selected=run([gcc,'-print-prog-name='+name],'native-program-'+name).strip()
        selected_path=Path(selected)
        if not selected_path.is_absolute():
            selected_path=Path(shutil.which(selected,path=ENVIRONMENT['PATH']) or '')
        require(selected_path.is_file(),'Native compiler helper unavailable: '+name)
        native_tools[name]=str(pin_installed(selected_path))
    # Original test/fixture sources are unchanged; copied runner links the new
    # extension too, exercising finite semantics with attachment left empty.
    # ASan reserves a large virtual shadow; RSS/wall/CPU/file bounds still apply.
    original=json.loads(run([sys.executable,'scripts/check_endpoint_native.py'],'original-native',sanitizer=True))
    original_receipt=json.loads((PROJECT/'artifacts/verification/endpoint-native.json').read_text())
    require(original_receipt['compiler']['path']==str(gcc) and
            original_receipt['compiler']['sha256']==INSTALLED_PINS[str(gcc)],
            'Original suite selected a different native compiler')
    inputs=[path for path,_ in UNITS]+['tests/reference_link.c','tests/avr_runtime_probe.c']
    macros=['-DHMS_AVR_UART_TEST','-DHMS_AVR_USART_TEST','-DHMS_AVR_CLOCK_TEST','-DHMS_AVR_EEPROM_TEST']
    reports={};standing_reports={}
    for mode in ('plain','asan'):
        flags=['-O2'] if mode=='plain' else ['-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie']
        exe=BUILD/('runtime-'+mode)
        run([gcc,*COMMON,*flags,*macros,*inputs,'-o',exe],'compile-'+mode)
        reports[mode]=json.loads(run([exe],'probe-'+mode,sanitizer=mode=='asan'))
        require(reports[mode]['cases']==11 and reports[mode]['wireOracleSteps']==20000,'Probe coverage changed')
        standing_exe=BUILD/('standing-'+mode)
        standing_inputs=['protocol/serial/frame.c','protocol/endpoint/endpoint.c',
                         'protocol/endpoint/standing.c','protocol/endpoint/link.c',
                         'tests/standing_fixture.c','tests/standing_controls.c']
        run([gcc,*COMMON,*flags,*standing_inputs,'-o',standing_exe],'standing-compile-'+mode)
        standing_reports[mode]=json.loads(run([standing_exe],'standing-probe-'+mode,sanitizer=mode=='asan'))
        require(standing_reports[mode]['cases']==13,'Standing control coverage changed')
        require(standing_reports[mode]['physical_qualification'] is False,'Synthetic controls overclaimed')
    return {'original':original,'integration':reports,'standing':standing_reports,
            'compiler_path':str(gcc),'compiler_sha256':digest(gcc),'compiler_version':version,
            'selected_native_tools':native_tools}

def pinned_tools(binary):
    require(digest(ARCHIVE)==ARCHIVE_SHA,'Approved compiler archive differs')
    pin_installed(ARCHIVE,ARCHIVE_SHA,critical=False)
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
        pin_installed(path,hashes[member],critical='/bin/' in str(path) or '/libexec/' in str(path))
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
    target_units=[pair for pair in UNITS if pair[0]!='tests/endpoint_fixture.c']
    target_units += [('tests/standing_fixture.c','standing-fixture'),('tests/standing_target.c','target')]
    for source,unit in target_units:
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
    require(allocations['hms_target_arena']==256,'Primitive reservation changed')
    require(allocations['hms_target_standing']+allocations['hms_target_controller']+
            allocations['hms_target_glue_reserve']+2==160,'Standing128+glue32 accounting changed')
    require(allocations['hms_target_protection_reserve']==64,'Protection reservation changed')
    require({'__vector_13','__vector_18'}<={s['name'] for s in symbols},'Timer1/USART RX vector missing')
    write_json(BUILD/'stack-records.json',records);write_json(BUILD/'symbols.json',symbols)
    flash=sections.get('.text',0)+sections.get('.data',0)
    static=sum(sections.get(name,0) for name in ('.data','.bss','.noinit'))
    return {'compiler_version':version,'toolchain_pins':pins,'mcu':'atmega328p','declared_f_cpu_hz':16000000,
            'flags':AVR_FLAGS,'flash_bytes':flash,'static_sram_bytes':static,'sections':sections,'allocations':allocations,
            'limits':{'physical_flash':32768,'uno_application_flash':32256,'sram':2048,'eeprom':1024},
            'static_plus_512_stack_bytes':static+512,'new_static_delta_from_sealed_baseline':static-1343,
            'standing_static_delta_ceiling_fits':static-1343<=160,
            'static_reservation_arithmetic_fits':flash<=32256 and static+512<=2048 and static-1343<=160,
            'combined_foreground_isr_stack_analysis':'PENDING: old no-ISR fixture bound is inapplicable',
            'tx_register_instruction_window_review':'PENDING: inspect exact linked sequence and max baud interval',
            'target_runtime_fit_demonstrated':False,'target_executed':False}

def prepare_owner():
    global OWNER,RUNTIME_FD,RUNTIME_SHA
    require(sys.platform=='linux' and os.uname().machine=='x86_64' and sys.flags.optimize==0 and
            sys.implementation.name=='cpython' and sys.version_info[:2]==(3,12),
            'Runner owner profile requires the reviewed Linux/x86-64/CPython3.12 host')
    require(hasattr(os,'pidfd_open') and hasattr(signal,'pidfd_send_signal') and
            hasattr(os,'WNOWAIT') and hasattr(os,'memfd_create'),'Owner kernel interfaces unavailable')
    rows=json.loads((BUILD/'runner-owner-pins.json').read_text())['files']
    require(len(rows)==4,'Unexpected owner dependency set')
    for row in rows:
        target=BUILD/row['target']
        require(target.stat().st_size==row['bytes'] and digest(target)==row['sha256'],'Frozen owner input differs')
        pin_installed(REPO/row['source'],row['sha256'],critical=True)
    executable=pin_installed(Path(sys.executable).resolve())
    RUNTIME_FD=os.open('/proc/self/exe',os.O_RDONLY|os.O_CLOEXEC)
    RUNTIME_SHA=fd_digest(RUNTIME_FD)
    require(RUNTIME_SHA==digest(executable),'Running interpreter differs from selected interpreter')
    # Only this exact reviewed helper module is imported from the private copy.
    # It does not import controller C or endpoint Python modules.
    spec=importlib.util.spec_from_file_location('hms_standing_runner_owner',BUILD/'runner-owner-inputs/guardian.py')
    require(spec is not None and spec.loader is not None,'Owner module loader unavailable')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    previous=signal.pthread_sigmask(signal.SIG_BLOCK,BLOCKED)
    try:
        require(not pending_interrupts(),'Interrupt pending before owner preparation')
        OWNER=module.Guardian(BUILD/'runner-owner-inputs/libharness-owner.so')
        owner_precondition();require(OWNER.empty(),'Dedicated runner did not begin child-free')
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK,previous)

def final_audit(report):
    global RUNTIME_FD
    errors=[];owner_closed=False;owner_empty=OWNER is None
    if OWNER is not None:
        try:
            OWNER.settle(seconds=8);owner_empty=OWNER.empty()
            report['owned_children_reaped']=list(OWNER.records)
            for process in PROCESS_OBJECTS:
                matches=[record for record in OWNER.records if record['pid']==process.pid]
                if matches:process.returncode=matches[-1]['exitCode']
            OWNER.close();owner_closed=True
        except BaseException as error:
            errors.append(type(error).__name__+': '+str(error))
    after=input_snapshot();runtime=runtime_snapshot();installed=installed_snapshot()
    report.update(source_hashes_after=after['original'],copied_source_hashes_after=after['frozen'],
        sources_unchanged=after['original']==SOURCE_PINS,copied_sources_unchanged=after['frozen']==SOURCE_PINS,
        runtime_after=runtime,runtime_sha256=RUNTIME_SHA,runtime_unchanged=runtime_stable(runtime),
        installed_file_pins=dict(INSTALLED_PINS),installed_file_hashes_after=installed,
        installed_files_unchanged=installed==INSTALLED_PINS,
        owner_empty=owner_empty,owner_closed=owner_closed,owner_cleanup_errors=errors,
        interrupts_pending_after_cleanup=pending_interrupts(),commands=commands)
    audits=[]
    for command in commands:
        if command['pgid'] is None:continue
        try:audits.append({'pgid':command['pgid'],'members':group_members(command['pgid'])})
        except BaseException as error:audits.append({'pgid':command['pgid'],'error':type(error).__name__+': '+str(error)})
    report['final_group_audit']=audits
    report['owned_groups_observed_absent']=all(a.get('members')==[] for a in audits)
    report['post_reap_audit_scope']='Numeric PGID observation only; never confers authority and never causes a post-reap signal'
    if not (input_stable(after) and runtime_stable(runtime) and installed==INSTALLED_PINS and
            owner_empty and owner_closed and not errors and not report['interrupts_pending_after_cleanup'] and
            report['owned_groups_observed_absent'] and all(c['passed'] for c in commands)):
        report['requested_checks_completed']=False
    if RUNTIME_FD is not None:
        os.close(RUNTIME_FD);RUNTIME_FD=None

def main():
    global BUILD,PROJECT,SOURCE_PINS,FINAL_DESTINATION,FINAL_REPORT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('stage',choices=('native','avr'))
    parser.add_argument('--attempt',type=int,default=1)
    parser.add_argument('--toolchain-bin',type=Path,default=DEFAULT_BIN);opts=parser.parse_args()
    def interrupted(signum, _frame):
        raise RuntimeError('Runner interrupted by signal '+str(signum))
    signal.signal(signal.SIGINT,interrupted);signal.signal(signal.SIGTERM,interrupted)
    os.umask(0o077);sys.dont_write_bytecode=True
    require(opts.attempt>0,'Attempt must be positive')
    suffix='' if opts.attempt==1 else '-attempt-'+str(opts.attempt)
    BUILD=HERE/'build'/(opts.stage+suffix)
    destination=HERE/('checks-'+opts.stage+suffix+'.json')
    require(not destination.exists() and not BUILD.exists(),'Attempt already exists; preserve it and select a new explicit --attempt')
    BUILD.mkdir(parents=True,exist_ok=False,mode=0o700)
    report={'schema':'hms-standing-endpoint-controller-checks/1','recorded_at':datetime.now(timezone.utc).isoformat(),
        'stage':opts.stage,'attempt':opts.attempt,'public_edits':False,'target_executed':False,
        'requested_checks_completed':False,'source_preparation_completed':False,
        'source_snapshot_basis':'Private source byte copies verified before/after; no filesystem immutability or full dependency-closure claim',
        'frozen_source_copy_root':str(BUILD.relative_to(HERE)),
        'dependency_scope':'Pinned interpreter ELF, selected compiler/tool binaries, borrowed helper bytes and explicit source inputs. AVR archive headers/libraries/specs are pinned too. Native system headers/start objects/libraries, host stdlib and dynamic loader remain trusted unpinned dependencies; not a complete native-toolchain qualification.',
        'owner_scope':'Dedicated sole-thread live subreaper, raw SIGCHLD default/no NOCLDWAIT; no competing reaper. Orderly INT/TERM cleanup only; runner SIGKILL/host failure not qualified.',
        'resource_scope':'Per-process rlimits plus20ms PGID RSS observations and wall timeout; not a cgroup quota, hostile-process sandbox, or universal containment'}
    FINAL_DESTINATION=destination;FINAL_REPORT=report
    write_json(destination,report)
    try:
        sources={str(p.relative_to(HERE)):digest(p) for p in sorted(PROJECT.rglob('*'))
                 if p.is_file() and 'artifacts' not in p.relative_to(PROJECT).parts and '__pycache__' not in p.parts}
        fixed=['run_checks.py','PLAN.md','WIRE.md','wire-vectors.json','source-pins.json',
               'README.md','REVIEW.md','project-source-review.json','project-source-diff.patch',
               'runner-owner-pins.json','RUNNER-REVIEW.md']
        fixed += [row['target'] for row in json.loads((HERE/'runner-owner-pins.json').read_text())['files']]
        for name in fixed:sources[name]=digest(HERE/name)
        SOURCE_PINS=sources;report['sources']=dict(sources)
        save_new(BUILD/'freeze-intent.json',{'sources':sources,'child_launched':False})
        for name,value in sources.items():
            target=BUILD/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with (HERE/name).open('rb') as source,target.open('xb') as copied:shutil.copyfileobj(source,copied)
            require(digest(target)==value,'Source changed while preparing private byte copy: '+name)
        PROJECT=BUILD/'project';report['source_preparation_completed']=True
        require(input_stable(input_snapshot()),'Sources changed during copy')
        prepare_owner()
        report['owner_preconditions_checked']=True
        report['owner_preconditions']={'pid':os.getpid(),'native_thread':threading.get_native_id(),
            'raw_sigchld_snapshot':OWNER.helper.hms_owner_signal_snapshot(),
            'native_threads':len(os.listdir('/proc/self/task')),'subreaper':OWNER.helper.hms_subreaper_get(),
            'initial_children_absent':OWNER.empty(),'python_optimization_disabled':sys.flags.optimize==0}
        report['runtime_before']=runtime_snapshot()
        write_json(destination,report)
        if opts.stage=='native':report['native']=native()
        else:report['avr']=avr(opts.toolchain_bin)
        report['requested_checks_completed']=True
    except BaseException as error:
        report['requested_checks_completed']=False;report['error']=type(error).__name__+': '+str(error)
    finally:
        previous=signal.pthread_sigmask(signal.SIG_BLOCK,BLOCKED)
        try:
            final_audit(report);write_json(destination,report)
        finally:
            # The outer entrypoint catches an interrupt delivered here and
            # records failure after settlement instead of leaving a passing
            # stage receipt merely because the signal had been deferred.
            signal.pthread_sigmask(signal.SIG_SETMASK,previous)
    require(report['requested_checks_completed'],'Checks did not complete; see '+str(destination))
    print(json.dumps({'receipt':str(destination),'requested_checks_completed':True,
                      'target_executed':False,'runtime_fit_claimed':False}))

def publish_terminal_failure(error):
    # Terminal path: leave INT/TERM blocked until process exit so publication
    # cannot be interrupted a second time after children have been settled.
    signal.pthread_sigmask(signal.SIG_BLOCK,BLOCKED)
    if FINAL_REPORT is not None and FINAL_DESTINATION is not None:
        FINAL_REPORT['requested_checks_completed']=False
        FINAL_REPORT['terminal_failure']=type(error).__name__+': '+str(error)
        FINAL_REPORT['interrupts_pending_at_terminal_failure']=pending_interrupts()
        write_json(FINAL_DESTINATION,FINAL_REPORT)

if __name__=='__main__':
    try:main()
    except BaseException as error:
        publish_terminal_failure(error)
        raise
