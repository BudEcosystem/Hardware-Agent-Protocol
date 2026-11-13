#!/usr/bin/env python3
"""Build/test original finite boot reservations; optionally cross-compile only.

No EEPROM, board, target program or acquired implementation is executed.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import posixpath
import re
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT/'artifacts/verification/boot-epoch-build'
OUTPUT = ROOT/'artifacts/verification/boot-epoch.json'
ARCHIVE = ROOT/'research/constrained/avr/raw/avr-gcc-7.3.0-atmel3.6.1-arduino7-x86_64-pc-linux-gnu.tar.bz2'
ARCHIVE_SHA = 'bd8c37f6952a2130ac9ee32c53f6a660feb79bee8353c8e289eb60fdcefed91e'
FILES = ['protocol/platform/boot_epoch.c','protocol/platform/boot_epoch.h',
         'tests/boot_epoch_tests.c','tests/boot_epoch_avr_probe.c','protocol/endpoint/endpoint.c',
         'protocol/endpoint/endpoint.h','tests/endpoint_fixture.c','tests/endpoint_fixture.h',
         'scripts/check_boot_epoch.py']
UNITS = ['protocol/platform/boot_epoch.c','protocol/endpoint/endpoint.c','tests/endpoint_fixture.c','tests/boot_epoch_tests.c']
COMMON = ['-std=c11','-g','-Wall','-Wextra','-Wconversion','-Werror','-Wvla','-fno-common']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(path):
    return {'path':str(path.relative_to(ROOT)),'sha256':sha(path)}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-only',action='store_true')
    parser.add_argument('--toolchain-bin',type=Path,default=Path('/tmp/hms-avr-toolchain-7.3.0-atmel3.6.1-arduino7/avr/bin'))
    args=parser.parse_args()
    before={p:sha(ROOT/p) for p in FILES}
    BUILD.mkdir(parents=True,exist_ok=True)
    commands=[]
    excluded={'GCC_EXEC_PREFIX','COMPILER_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','OBJC_INCLUDE_PATH',
              'LIBRARY_PATH','LD_PRELOAD','LD_LIBRARY_PATH','LD_AUDIT','DEPENDENCIES_OUTPUT','SUNPRO_DEPENDENCIES'}
    base_environment={key:value for key,value in os.environ.items() if key not in excluded}
    base_environment['LC_ALL']='C'
    def run(command, *, env=None):
        result=subprocess.run([str(v) for v in command],cwd=ROOT,env=base_environment if env is None else env,capture_output=True,text=True,timeout=90)
        commands.append({'argv':[str(v) for v in command],'exit_code':result.returncode,
                         'stdout':result.stdout,'stderr':result.stderr})
        (BUILD/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        require(result.returncode==0,'Command failed: '+str(command)+'\n'+result.stderr)
        return result.stdout
    gcc=Path(shutil.which('gcc')).resolve()
    compiler={'path':str(gcc),'sha256':sha(gcc),'version':run([gcc,'--version']).splitlines()[0]}
    environment=base_environment.copy()
    environment.update(ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    native=[]
    outputs=[]
    for name,flags in [('plain',['-O2']),('asan',['-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie'])]:
        binary=BUILD/('boot-epoch-'+name)
        run([gcc,*COMMON,*flags,*UNITS,'-o',binary])
        value=json.loads(run([binary],env=environment))
        require(value['cases']==11 and value['torn_byte_cases']==1792 and value['power_cut_boundaries']==84 and
                value['rollback_counterexample_demonstrated'], 'Unexpected finite fault-model coverage')
        native.append({'variant':name,'flags':COMMON+flags,'results':value})
        outputs.append(record(binary))
    avr=None
    if not args.native_only:
        require(sha(ARCHIVE)==ARCHIVE_SHA,'Compiler archive pin changed')
        archive_hashes,links={},{}
        with tarfile.open(ARCHIVE,'r|bz2') as source:
            for member in source:
                if member.isfile():
                    digest=hashlib.sha256()
                    with source.extractfile(member) as data:
                        for chunk in iter(lambda:data.read(1024*1024),b''):
                            digest.update(chunk)
                    archive_hashes[member.name]=digest.hexdigest()
                elif member.islnk():
                    links[member.name]=member.linkname
                elif member.issym():
                    links[member.name]=posixpath.normpath(posixpath.join(posixpath.dirname(member.name),member.linkname))
        for _ in range(len(links)):
            resolved={name:archive_hashes[target] for name,target in links.items() if target in archive_hashes}
            if not resolved: break
            archive_hashes.update(resolved)
            for name in resolved: del links[name]
        toolroot=args.toolchain_bin.resolve().parent
        pins={}
        def pin(path):
            path=Path(path).resolve()
            require(path.is_relative_to(toolroot),'Toolchain dependency outside approved tree')
            member='avr/'+str(path.relative_to(toolroot))
            digest=sha(path)
            require(digest==archive_hashes.get(member),'Toolchain/archive mismatch: '+str(path))
            pins[str(path)]={'archive_member':member,'sha256':digest}
            return path
        tools={name:pin(toolroot/'bin'/('avr-'+name)) for name in ('gcc','as','size','nm','objdump')}
        pin(toolroot/'libexec/gcc/avr/7.3.0/cc1')
        pin(toolroot/'lib/gcc/avr/7.3.0/device-specs/specs-atmega328p')
        for header in ('lib/gcc/avr/7.3.0/include/stdint.h','avr/include/stdint.h','lib/gcc/avr/7.3.0/include/stddef.h'):
            pin(toolroot/header)
        flags=['-mmcu=atmega328p','-std=c11','-Os','-Wall','-Wextra','-Wconversion','-Werror','-Wvla',
               '-fno-common','-ffunction-sections','-fdata-sections','-fstack-usage','-MD']
        objects=[]
        for unit,name in [('protocol/platform/boot_epoch.c','boot_epoch'),('tests/boot_epoch_avr_probe.c','abi_probe')]:
            obj=BUILD/(name+'.o')
            run([tools['gcc'],*flags,'-c',unit,'-o',obj])
            # The compiler and every acquired header are verified against the
            # approved archive. Original source dependencies stay in ROOT.
            dependencies=(BUILD/(name+'.d')).read_text().replace('\\\n',' ').split(':',1)[1].split()
            for dep in dependencies:
                path=Path(dep)
                if not path.is_absolute():path=ROOT/path
                path=path.resolve()
                if path.is_relative_to(toolroot):pin(path)
                else:require(path.is_relative_to(ROOT),'Unexpected source dependency')
            objects.append(obj)
            outputs.extend(record(BUILD/(name+suffix)) for suffix in ('.o','.d','.su'))
        sections=run([tools['size'],'-A',*objects])
        symbols=run([tools['nm'],'-S','--size-sort',*objects])
        disassembly=run([tools['objdump'],'-dr',objects[0]])
        for name,data in [('sections.txt',sections),('symbols.txt',symbols),('disassembly.txt',disassembly)]:
            path=BUILD/name;path.write_text(data);outputs.append(record(path))
        sizes={name:int(size,16) for size,name in re.findall(r'^\S+\s+([0-9a-fA-F]+)\s+\w\s+(hms_boot_\w+_abi_size)$',symbols,re.M)}
        require(sizes=={'hms_boot_reservation_abi_size':12,'hms_boot_storage_abi_size':14},'AVR ABI size changed')
        avr={'target':'atmega328p','executed':False,'linked_firmware':False,'flags':flags,
             'reservation_ram_bytes':12,'storage_config_ram_bytes':14,
             'stack_scope':'Per-function compiler reports only; no callback/interrupt/whole-firmware stack bound.',
             'toolchain_archive':record(ARCHIVE),'toolchain_files':pins}
    require(before=={p:sha(ROOT/p) for p in FILES},'Original inputs changed during verification')
    outputs.append(record(BUILD/'commands.json'))
    report={'schema':'hms-finite-boot-reservation/1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'passed':True,'command':'python3 scripts/check_boot_epoch.py'+(' --native-only' if args.native_only else ''),
        'compiler':compiler,'host':platform.platform(),'native':native,'avr':avr,
        'fault_model':'Previously completed cells/header remain stable; failed/interrupted programming may leave any byte value only in the selected previously-erased cell; qualified reads/completion; exclusive startup owner.',
        'limits':['Finite one-byte-per-reservation bank; no erasure, wrap, recycle, autoformat or repair.',
                  'No EEPROM, board, MCU emulator, acquired target code or physical power interruption executed.',
                  'Tested rollback counterexample intentionally demonstrates that an erased highest completed cell can reuse an epoch outside the model.',
                  'Power/reset/BOD correctness, retention, target-only write containment and timing remain platform qualification requirements.',
                  'AVR object/ABI reports do not establish linked firmware fit, real EEPROM driver behavior or bounded interrupts.'],
        'files':[{'path':p,'sha256':h} for p,h in before.items()],'outputs':outputs}
    OUTPUT.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'native_variants':len(native),'cases_per_variant':11,
                      'avr_cross_compiled':avr is not None,'artifact':str(OUTPUT.relative_to(ROOT))}))


if __name__=='__main__':
    main()
