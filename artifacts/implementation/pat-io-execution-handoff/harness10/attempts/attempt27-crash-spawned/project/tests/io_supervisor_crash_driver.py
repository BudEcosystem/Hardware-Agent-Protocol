"""Original fixed test driver: hard owner exit at one declared checkpoint."""
import json
import os
from pathlib import Path
import re
import socket
import stat
import sys

os.umask(0o077);sys.dont_write_bytecode=True
assert sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
assert len(sys.argv)==2
prepared=Path(sys.argv[1]);config_path=prepared/'driver-config.json';info=config_path.lstat()
assert stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and info.st_mode&0o777==0o600 and info.st_size<=65536
config=json.loads(config_path.read_bytes())
assert set(config)=={'root','phase','externalRoots'} and config['phase'] in {'admitted','launching','spawned','producer_settled','archived'}
assert type(config['root']) is str and Path(config['root'])==prepared.parent/'supervisor'
assert type(config['externalRoots']) is list and 1<=len(config['externalRoots'])<=7
assert all(type(p) is str and Path(p).is_absolute() for p in config['externalRoots'])
project=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(project),str(project/'supervisor')]+config['externalRoots']
def no_network(*args,**kwargs):raise RuntimeError('TEST_DRIVER_NETWORK_FORBIDDEN')
class NoSocket(socket.socket):
    def __new__(cls,*args,**kwargs):return no_network()
socket.socket=NoSocket;socket.create_connection=no_network;socket.getaddrinfo=no_network
launches=[]
def audit(event,args):
    if event=='open' and isinstance(args[0],(str,bytes)) and Path(os.fsdecode(args[0])).suffix=='.pyc':
        raise FileNotFoundError('Use reviewed source bytes')
    if event=='subprocess.Popen':
        executable,argv,cwd,environment=args
        entry=Path(argv[3]) if type(argv) in (list,tuple) and len(argv)==7 else Path('/invalid')
        assert not launches and executable==sys.executable and argv[:3]==[sys.executable,'-I','-B']
        assert entry.name=='worker_entry.py' and entry.parent.name=='supervisor'
        assert entry.parent.parent.parent==Path(config['root']) and re.fullmatch(r'code-[0-9a-f]{64}',entry.parent.parent.name)
        assert str(cwd)==str(entry.parent.parent) and all(type(p) is str and p.isdecimal() for p in argv[4:])
        assert environment=={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'}
        launches.append(str(entry))
    elif event.startswith('socket.') or event in {'os.system','os.exec','os.fork','os.forkpty','os.posix_spawn'}:
        raise RuntimeError('Only the declared original supervisor worker may launch')
    if event=='sqlite3.connect':assert Path(os.fsdecode(os.fspath(args[0])))==Path(config['root'])/'attempts.db'
sys.addaudithook(audit)
from supervisor_contracts import document,read_file,write_file
from bundle_io import load_bundle
from qualification_supervisor import QualificationSupervisor
from hms.contracts import canonical

fd=os.open(prepared,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
request=document(read_file(fd,'request.json'));bundle=load_bundle(fd,request)
service=QualificationSupervisor(config['root'],create=True)
def crash(phase,row):
    if phase==config['phase']:
        write_file(fd,'crash-receipt.json',canonical(dict(phase=phase,record=row['record'],hardExitCode=91,launches=launches)))
        os._exit(91)
service._checkpoint=crash
service.execute(request,bundle)
raise AssertionError('Declared crash checkpoint was not reached')
