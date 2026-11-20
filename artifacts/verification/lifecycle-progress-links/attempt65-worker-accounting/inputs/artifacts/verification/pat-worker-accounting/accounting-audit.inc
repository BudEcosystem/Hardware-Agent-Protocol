    # Independently derive observations; never import the observer or project code.
    accounting=read(ATTEMPT/'worker-accounting.json')
    launches=read(ATTEMPT/'worker-accounting-launch-audit.json')
    assert len(launches)==1 and launches[0]['testId']==targets[0]==accounting['testId']
    assert accounting['profile']=='hms.worker-resource-observation/1' and accounting['errors']==[]
    observed=accounting['launch'];terminal=observed['terminal']
    assert observed['launchFailure'] is None and observed['pid']==record['pid']
    assert observed['argv']==launches[0]['argv'] and launches[0]['cwd']==str(image)
    assert observed['argv'][:4]==[read(ATTEMPT/'child-runtime.json')['executable'],'-I','-B',str(image/'supervisor/worker_entry.py')]
    assert terminal['observedBy']=='original-poll' and terminal['returnCode']==report['exitCode']==-15
    assert observed['before']['afterMonotonicNs']<=observed['launchedMonotonicNs']<=terminal['snapshot']['beforeMonotonicNs']
    for name,position,path in (('attemptDirectory',4,worker),('input',5,worker/'input.json'),('writerLease',6,worker/'writer.lease')):
        info=path.lstat();description=observed['descriptors'][name]
        assert description['available'] and description['descriptor']==int(observed['argv'][position])
        for key,value in dict(device=info.st_dev,inode=info.st_ino,uid=info.st_uid,mode=stat.S_IMODE(info.st_mode),fileType=stat.S_IFMT(info.st_mode)).items():
            assert description[key]==value
        if name!='attemptDirectory':assert description['size']==info.st_size
    assert record['lease']=={key:str(observed['descriptors']['writerLease'][key]) for key in ('device','inode')}
    launch_input=read(worker/'input.json')
    assert launch_input==dict(profile='hms.pat.io-supervisor-launch/0.1',attemptId=record['attemptId'],request=request)
    assert (worker/'input.json').read_bytes()==canonical(launch_input)
    start_snapshot=accounting['testStart'];before_snapshot=observed['before']
    reaped_snapshot=terminal['snapshot'];finish_snapshot=accounting['testFinish']
    start_receipt=read(ATTEMPT/'worker-accounting-start.json')
    launch_receipt=read(ATTEMPT/'worker-accounting-launch.json')
    terminal_receipt=read(ATTEMPT/'worker-accounting-terminal.json')
    assert start_receipt['testStart']==start_snapshot and start_receipt['launch'] is None
    assert launch_receipt['launch']['before']==before_snapshot and launch_receipt['launch']['pid'] is None
    assert launch_receipt['launch']['terminal'] is None and terminal_receipt['launch']==observed
    assert terminal_receipt['testFinish'] is None
    additive=('ru_utime','ru_stime','ru_minflt','ru_majflt','ru_inblock','ru_oublock','ru_nvcsw','ru_nivcsw')
    raw_fields=set(additive)|{'ru_maxrss','ru_ixrss','ru_idrss','ru_isrss','ru_nswap','ru_msgsnd','ru_msgrcv','ru_nsignals'}
    snapshots=(start_snapshot,before_snapshot,reaped_snapshot,finish_snapshot)
    for position,snapshot in enumerate(snapshots):
        assert snapshot['beforeMonotonicNs']<=snapshot['afterMonotonicNs']
        if position:assert snapshots[position-1]['afterMonotonicNs']<=snapshot['beforeMonotonicNs']
        for scope in ('self','children'):
            raw_usage=snapshot['usage'][scope]
            assert raw_usage['available'] and set(raw_usage['raw'])==raw_fields
            assert all(type(value) in (int,float) and 0<=value<float('inf') for value in raw_usage['raw'].values())
        assert set(snapshot['pressure'])=={'cpu','memory','io'}
        for pressure in snapshot['pressure'].values():
            if pressure['available']:assert len(pressure['raw'].encode('ascii'))<=4096
            else:assert 'raw' not in pressure and type(pressure['errorType']) is str
    assert start_snapshot['usage']['children']==before_snapshot['usage']['children']
    assert reaped_snapshot['usage']['children']==finish_snapshot['usage']['children']
    for label,first,last in (('testDelta',start_snapshot,finish_snapshot),('launchToReapDelta',before_snapshot,reaped_snapshot)):
        derived={scope:{'available':True,'additiveCounters':{field:last['usage'][scope]['raw'][field]-first['usage'][scope]['raw'][field]
            for field in additive}} for scope in ('self','children')}
        assert derived==accounting[label]
        assert all(value>=0 for item in derived.values() for value in item['additiveCounters'].values())
    wall_bounds=[(reaped_snapshot['beforeMonotonicNs']-before_snapshot['afterMonotonicNs'])/1e9,
                 (reaped_snapshot['afterMonotonicNs']-before_snapshot['beforeMonotonicNs'])/1e9]
    interval=accounting['launchToReapDelta']
    cpu_seconds={scope:sum(interval[scope]['additiveCounters'][name] for name in ('ru_utime','ru_stime')) for scope in ('self','children')}
    observation=dict(associationVerified=True,directChildLaunches=1,originalAttemptId=record['attemptId'],pid=record['pid'],
        accountingSha256=sha(ATTEMPT/'worker-accounting.json'),launchAuditSha256=sha(ATTEMPT/'worker-accounting-launch-audit.json'),
        ownedObjectAndInheritedDescriptorsAssociated=True,pidBasedSampling=False,launchToReapWallSecondsBounds=wall_bounds,
        launchToReapCpuSeconds=cpu_seconds,launchToReapAdditiveCounters=interval,
        testAdditiveCounters=accounting['testDelta'],rawChildPeakRssKiB=reaped_snapshot['usage']['children']['raw']['ru_maxrss'],
        snapshotDurationsNs=[s['afterMonotonicNs']-s['beforeMonotonicNs'] for s in snapshots],
        globalPressureAvailable={name:all(s['pressure'][name]['available'] for s in snapshots) for name in ('cpu','memory','io')},
        childUsageOutsideObservedIntervalUnchanged=True,schedulingWaitCauseMeasured=False,
        parentFunctionAttributionMeasured=False,observerOverheadEliminated=False,
        deploymentTimingQualified=False)
