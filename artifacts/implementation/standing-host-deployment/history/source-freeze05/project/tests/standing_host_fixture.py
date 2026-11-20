"""Original installed test assembly; no application path/command selection."""
import copy
import fcntl
import stat
import json
import os
from pathlib import Path
import select
import socket
import struct
import time

from hms.contracts import canonical
from hms.journal import Context, Journal
from hms import resource_topology as graph
from hms import standing_contracts as c
from hms.standing_endpoint import StandingHost, InstalledNativeDriver
from hms.endpoint_transport import LocalEndpointStream
from hms.standing_pat import InstalledNativeProducer, StandingCatalog, installed_artifact, SOURCE_PINS, EVALUATOR
from hms.standing_store import StandingStore

OWNER=Context('native-standing-owner','simulation:standing-host')


def installation(pipe_image,qualification_image):
    def node(kind,properties=None,*,contains=(),requires=()):
        return {'kind':kind,'properties':properties or {},'contains':list(contains),'requires':list(requires)}
    pins=dict(SOURCE_PINS)
    pins['tests/standing_host_pipe.c']=c.sha((c.ROOT/'tests/standing_host_pipe.c').read_bytes())
    driver=c.identity('HMS-STANDING-PIPE-SOURCES-v0.1',pins)
    nodes={'hub':node('hub',contains=('board','service')),
        'board':node('board',contains=('demand','output','demand-access','output-access')),
        'service':node('service',{'serviceProfile':'synthetic-service/0.1'},contains=('driver',),requires=('hub',)),
        'driver':node('driver',{'driverProfile':'synthetic-io-hub/0.1','implementationDigest':driver},requires=('service',)),
        'demand-access':node('gpio_access',{'pin':'demand'},requires=('driver',)),
        'output-access':node('gpio_access',{'pin':'output'},requires=('driver',))}
    for name in ('demand','output'):
        nodes[name]=node('pin',{'electrical':{'evidenceMode':'simulation','nominalMilliVolt':3300,
            'maxSourceMicroAmp':10000,'maxSinkMicroAmp':10000,
            'modes':['digital_input','push_pull_output'],'idleMode':'high_impedance'}})
    atoms={name:{'node':which,'purpose':purpose} for name,which,purpose in (
        ('atom:demand','demand','exclusive_hardware'),('atom:output','output','exclusive_hardware'),
        ('atom:slot','driver','lifecycle'),('atom:service','service','lifecycle'))}
    aliases={'alias:demand':{'node':'demand-access','includes':['atom:demand','atom:slot']},
             'alias:output':{'node':'output-access','includes':['atom:output','atom:slot']}}
    topology={'profile':graph.PROFILE,'topologyId':'native:standing-host','deployment':OWNER.deployment,
        'nodes':nodes,'atoms':atoms,'aliases':aliases,'consumers':[{'instanceId':name,'actionId':'control',
            'rootAliases':['alias:demand','alias:output'],'requires':[]} for name in ('native:standing','native:finite')]}
    generations={'profile':graph.GENERATION_PROFILE,'topologyDigest':graph.topology_digest(topology),
                 'revision':1,'nodes':{name:'generation:1' for name in nodes}}
    return c.parse_installation({'profile':c.PROFILE,'deployment':OWNER.deployment,'routeId':'native:standing-route',
        'instanceId':'native:standing','finiteInstanceId':'native:finite','topology':topology,'generations':generations,
        'hardwareResources':['atom:demand','atom:output'],'slotResource':'atom:slot',
        'endpoint':{'incarnationHex':bytes(range(0xa0,0xb0)).hex(),'firmwareHex':bytes(range(0xb0,0xd0)).hex(),
            'manifestHex':bytes(range(0xc0,0xe0)).hex(),'boot':1,'kernel':1,'mask':3,'epochs':[1,1]},
        'driverImageDigest':c.sha(Path(pipe_image).read_bytes()),'qualificationImageDigest':c.sha(Path(qualification_image).read_bytes()),
        'driverSourceDigest':driver,'hostImplementationDigest':c.implementation_identity(),'capacity':copy.deepcopy(c.CAPACITY)})


class Fixture:
    def __init__(self,guardian,directory,pipe_image,evidence,manifest,*,host_class=StandingHost,store_class=StandingStore):
        self.guardian=guardian;self.directory=Path(directory);self.directory.mkdir()
        self.pipe_image=Path(pipe_image).resolve();self.evidence=Path(evidence).resolve();self.manifest=manifest
        self.installation=installation(self.pipe_image,self.evidence/manifest['binaryPath'])
        self.host_class,self.store_class=host_class,store_class
        self.journal=self.stream=self.control=None;self.pid=None
        self.policy=c.InstalledPolicy(OWNER,self.installation)
        self.driver=InstalledNativeDriver(self.pipe_image,self.installation)
        self._clock=1000
        parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        control,child_control=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        executable=os.open(self.pipe_image,os.O_RDONLY|os.O_CLOEXEC)
        try:
            fcntl.flock(executable,fcntl.LOCK_SH|fcntl.LOCK_NB)
            before=os.fstat(executable)
            assert stat.S_ISREG(before.st_mode) and before.st_size<=2*1024*1024
            body=os.pread(executable,2*1024*1024+1,0);after=os.fstat(executable)
            signature=lambda info:(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
            assert signature(before)==signature(after) and len(body)==before.st_size
            assert c.sha(body)==self.installation['driverImageDigest']
            def native():
                parent.close();control.close()
                os.dup2(child.fileno(),0);os.dup2(child.fileno(),1)
                os.set_inheritable(child_control.fileno(),True)
                keep={0,1,2,executable,child_control.fileno()}
                for fd in range(3,64):
                    if fd not in keep:
                        try:os.close(fd)
                        except OSError:pass
                os.execve('/proc/self/fd/'+str(executable),[str(self.pipe_image),'--test-control-fd',str(child_control.fileno())],
                          {'LANG':'C','LC_ALL':'C'})
            self.pid=guardian.fork(native)
            self.stream=LocalEndpointStream(parent.fileno())
            self.control=control;control=None
            self.attach(create=True)
            self.host.initialize(OWNER)
        except BaseException:
            self.close();raise
        finally:
            os.close(executable);parent.close();child.close();child_control.close()
            if control is not None:control.close()

    def attach(self,*,create):
        self.journal=Journal(self.directory/'authority.db',self.policy,clock_ms=lambda:self._clock,
                             standing_profile=True,create=create)
        self.policy.journal=self.journal
        self.producer=InstalledNativeProducer(self.journal,self.evidence,manifest=self.manifest)
        self.catalog=StandingCatalog(self.journal,self.policy,self.producer,create=create)
        self.store=self.store_class(self.journal,self.policy,self.catalog,create=create)
        self.host=self.host_class(self.store,self.stream,self.driver)
        if create:
            artifact=self.catalog.publish(OWNER,installed_artifact(self.installation))
            self.catalog.record_evaluation(OWNER,artifact,EVALUATOR,self.manifest['runId'])
            self.catalog.promote(OWNER,artifact)
            self.namespace=self.journal.issue_namespace(OWNER,9000)['token']
        else:
            self.namespace=self.journal._db.execute('SELECT token FROM namespaces').fetchone()[0]

    def reopen(self):
        self.journal.close();self.attach(create=False)

    def command(self,opcode,value=0):
        packet=struct.pack('>BQ',opcode,value);end=time.monotonic()+1
        self.control.setblocking(False);offset=0;reply=b''
        while offset<len(packet):
            left=end-time.monotonic();assert left>0 and select.select([],[self.control],[],left)[1]
            offset+=self.control.send(packet[offset:])
        while len(reply)<9:
            left=end-time.monotonic();assert left>0 and select.select([self.control],[],[],left)[0]
            chunk=self.control.recv(9-len(reply));assert chunk;reply+=chunk
        kind,result=struct.unpack('>BQ',reply);assert kind==opcode
        return result

    def snapshot(self,selector):return self.command(5,selector)
    def cycle(self,tick):return self.command(2,tick)

    def request(self,key='application'):
        return {'protocol':c.REQUEST,'replayNamespace':self.namespace,'deploymentKey':key,
            'taskKind':'standing-cooling-control','inputProfile':'synthetic-demand-rpm-v1','parameters':{},
            'evidenceMode':'simulation','limits':{'activationCap':100,'commandedOnMs':500,
                'mutationRecords':128,'episodeRecords':32,'leaseHorizonMs':1000}}

    def finite_request(self,key='finite'):
        intent={'instanceId':'native:finite','actionId':'control','arguments':{},'requiredEffect':'capability_completion',
            'endpointSession':'native-boot:1','controlGeneration':'native-control:2','bindingGeneration':'native-binding:1',
            'calibrationRevision':'native-calibration:1','descriptionDigest':c.identity('HMS-STANDING-FINITE-CAPABILITY-v0.1',self.installation),
            'timing':{'notBeforeUnixMs':1000,'latestStartUnixMs':2000,'maxRunMs':100,'latestCompletionUnixMs':2500}}
        return canonical({'protocol':'hms.invoke/0.1','replayNamespace':self.namespace,'operationKey':key,'intent':intent})

    def close(self):
        if self.journal is not None:self.journal.close();self.journal=None
        if self.stream is not None:self.stream.close();self.stream=None
        if self.control is not None:self.control.close();self.control=None
        if self.pid is not None and self.pid in self.guardian.handles:
            result=self.guardian.wait_exit(self.pid)
            assert result['pid']==self.pid and result['reaped'] and result['exitCode']==0, 'Native fixture did not exit cleanly on EOF'
        self.pid=None

    def __enter__(self):return self
    def __exit__(self,*_):self.close()
