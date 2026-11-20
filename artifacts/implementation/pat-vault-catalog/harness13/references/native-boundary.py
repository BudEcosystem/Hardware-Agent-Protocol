native_load = None
native_image = None
native_scans = {}
NATIVE_DIGEST = 'ce475ab2a70fb94e84d5d2f2f4c22cb8858d3305005bd154ebda996aae0774ff'

def verify_native_image(value):
    descriptor = value['descriptor']
    info = os.fstat(descriptor)
    required = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SEAL
    return (stat.S_ISREG(info.st_mode) and info.st_nlink == 0 and info.st_uid == os.getuid()
        and info.st_dev == value['device'] and info.st_ino == value['inode']
        and 0 < info.st_size <= 65536 and not os.get_inheritable(descriptor)
        and fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) & required == required
        and hashlib.sha256(os.pread(descriptor, 65537, 0)).hexdigest() == NATIVE_DIGEST)

def native_boundary(event, args):
    global native_load, native_image
    if current_test not in config['targets']:
        prohibited.append(event)
        raise RuntimeError('Native retention is only authorized inside an exact selected control')
    expected = scratch / current_test.split('.')[-1] / 'supervisor'
    if event == 'hms.retention.load.v1':
        artifact = root / 'supervisor/retention_scan.so'
        if (native_load is not None or args != (str(artifact), NATIVE_DIGEST, 'hms.retention.linux-cpython312-x86_64/1')
                or acquired.get(str(artifact)) != NATIVE_DIGEST or sha(artifact) != NATIVE_DIGEST):
            prohibited.append(event)
            raise RuntimeError('Native artifact differs from exact acquired image')
        native_load = dict(artifactOrigin=str(artifact), sha256=NATIVE_DIGEST, profile=args[2])
    elif event == 'hms.retention.image.v1':
        if (native_load is None or native_image is not None or len(args) != 5
                or type(args[0]) is not str or re.fullmatch(r'/proc/self/fd/[0-9]+', args[0]) is None
                or args[1] != NATIVE_DIGEST or any(type(value) is not int for value in args[2:])):
            prohibited.append(event)
            raise RuntimeError('Unexpected native memory image')
        value = dict(origin=args[0], descriptor=int(args[0].rsplit('/', 1)[1]), sha256=args[1],
                     device=args[2], inode=args[3], requestedSeals=args[4])
        if not verify_native_image(value):
            prohibited.append(event)
            raise RuntimeError('Native memory image is not the exact sealed artifact')
        native_image = value
    elif event == 'hms.retention.scan.v1':
        valid = (native_image is not None and len(args) == 3 and type(args[0]) is bytes
                 and type(args[1]) is int and type(args[2]) is int)
        if valid:
            path = Path(os.fsdecode(args[0]))
            root_scan = path == expected
            attempt_scan = path.parent == expected and re.fullmatch(r'[0-9a-f]{32}', path.name) is not None
            valid = ((root_scan or attempt_scan) and 0 <= args[1] <= (262144 if root_scan else 8192)
                     and 0 <= args[2] <= (268435456 if root_scan else 67108864))
        if not valid:
            prohibited.append(event)
            raise RuntimeError('Native scan is outside the owned supervisor scope')
        key = str(path)
        entry = native_scans.setdefault(key, dict(path=key, calls=0, maxFiles=0, maxBytes=0))
        entry['calls'] += 1
        entry['maxFiles'] = max(entry['maxFiles'], args[1])
        entry['maxBytes'] = max(entry['maxBytes'], args[2])
    else:
        prohibited.append(event)
        raise RuntimeError('Unknown native retention event')

