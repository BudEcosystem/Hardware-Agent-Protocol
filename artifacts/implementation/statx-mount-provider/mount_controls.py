"""Synthetic refusal controls plus actual unprivileged descriptor/path queries."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import fixed_block as bd
import mount_identity as m

CHECKS = []
WORK = Path.cwd()


def check(name, condition):
    assert condition, name
    CHECKS.append(name)


def refuse(name, action, match, error=m.MountError):
    try:
        action()
    except error as exc:
        check(name, match in str(exc))
    else:
        raise AssertionError(name + ': accepted')


def line(identity, parent=1, mount=b'/fixture', device=b'8:1', kind=b'ext4', source=b'/dev/example'):
    return str(identity).encode() + b' ' + str(parent).encode() + b' ' + device + b' / ' + mount + b' rw - ' + kind + b' ' + source + b' rw\n'


def main():
    os.umask(0o077)
    old, top = line(9), line(100, 9)
    legacy = (100, 99, 8, 1)
    check('stacked mount ID 100 is selected exactly', m.select_mount(old + top, b'/fixture/image', legacy) == b'/fixture')
    refuse('ext4 underneath a non-ext4 top does not admit', lambda: m.select_mount(old + line(100, 9, kind=b'tmpfs'), b'/fixture/image', legacy), 'UNSUPPORTED_FILESYSTEM')
    check('record order does not decide mount', m.select_mount(top + old, b'/fixture/image', legacy) == b'/fixture')
    check('a source named dash is allowed', m.select_mount(line(100, source=b'-'), b'/fixture', legacy) == b'/fixture')
    check('root mount prefix works', m.select_mount(line(100, mount=b'/'), b'/fixture', legacy) == b'/')
    for number, (encoded, decoded) in enumerate([(b'/with\\040space', b'/with space'), (b'/tab\\011name', b'/tab\tname'),
            (b'/line\\012name', b'/line\nname'), (b'/back\\134slash', b'/back\\slash'),
            (b'/raw\r\v\f\xff', b'/raw\r\v\f\xff')]):
        check('mount path byte decoding ' + str(number), m.select_mount(line(100, mount=encoded), decoded + b'/image', legacy) == decoded)
    for name, body, expected in [
        ('missing ID', old, 'MOUNT_ID_MISSING'), ('duplicate ID', top + top, 'DUPLICATE'),
        ('bad device', line(100, device=b'8:2'), 'DEVICE_MISMATCH'),
        ('bad major', line(100, device=b'08:1'), 'INVENTORY_NUMBER'),
        ('bad ID', top.replace(b'100 ', b'0100 ', 1), 'INVENTORY_NUMBER'),
        ('zero ID', line(0), 'INVENTORY_NUMBER'),
        ('overflow ID', line(2**64), 'INVENTORY_NUMBER'),
        ('bad escape', line(100, mount=b'/fixture\\999'), 'INVENTORY_ESCAPE'),
        ('relative mount', line(100, mount=b'fixture'), 'INVENTORY_PATH'),
        ('component prefix mismatch', line(100, mount=b'/fix'), 'PATH_MISMATCH'),
        ('truncated line', top[:-1], 'BOUND_OR_FORMAT'), ('empty inventory', b'', 'BOUND_OR_FORMAT'),
        ('oversized inventory', b'x' * (m.BOUND + 1), 'BOUND_OR_FORMAT'),
        ('NUL', top + b'\0\n', 'BOUND_OR_FORMAT'), ('malformed separator', top.replace(b' - ', b' x '), 'FORMAT'),
        ('short record', b'100 9\n', 'FORMAT'), ('extra field', top[:-1] + b' x\n', 'FORMAT')]:
        refuse(name, lambda body=body: m.select_mount(body, b'/fixture/image', legacy), expected)
    unique = (2**31 + 100, 99, 8, 1)
    with patch.object(m, 'query', side_effect=[unique, legacy, unique]) as query, patch.object(m, 'inventory', return_value=top):
        pin = m.admit('/fixture', 7)
        check('admission brackets exact legacy join with unique queries', pin == unique + (100, b'/fixture') and query.call_count == 3)
    with patch.object(m, 'query', side_effect=[unique, (100, 98, 8, 1)]), patch.object(m, 'inventory') as inventory:
        refuse('identity mismatch before inventory refuses', lambda: m.admit('/fixture', 7), 'CHANGED_DURING_ADMISSION')
        check('mismatched identity does not read inventory', not inventory.called)
    with patch.object(m, 'query', side_effect=[unique, legacy, (unique[0] + 1, *unique[1:])]), patch.object(m, 'inventory', return_value=top):
        refuse('identity changed after inventory refuses', lambda: m.admit('/fixture', 7), 'CHANGED_DURING_ADMISSION')
    with patch.object(m, 'query', return_value=unique) as query:
        m.verify('/fixture', 7, pin); m.verify('/fixture', 7, pin)
        check('every verify queries current identity', query.call_count == 2)
    with patch.object(m, 'query', return_value=(unique[0] + 1, *unique[1:])):
        refuse('different unique mount refuses', lambda: m.verify('/fixture', 7, pin), 'MOUNT_CHANGED')
    for name, path in [('relative', 'fixture'), ('embedded NUL', '/a\0b'), ('long', '/' + 'a' * 4095)]:
        refuse('invalid path ' + name, lambda path=path: m.path_bytes(path), 'INVALID_MOUNT_PATH')
    check('filesystem surrogate encoding preserved', m.path_bytes('/x\udcff') == b'/x\xff')
    library = os.environ['HMS_MOUNT_LIBRARY']; wanted = os.environ['HMS_MOUNT_LIBRARY_SHA256']
    refuse('library hash mismatch refuses', lambda: m.Probe(library, '0' * 64), 'LIBRARY_IDENTITY')
    probe = m.Probe(library, wanted)
    first, second = WORK / 'first', WORK / 'second'
    first.mkdir(); second.mkdir(); (WORK / 'alias').symlink_to(first)
    fd = os.open(first, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        live = probe.query(first, fd)
        check('actual directory query matches fstat inode and device', live[1:] == (os.fstat(fd).st_ino, os.major(os.fstat(fd).st_dev), os.minor(os.fstat(fd).st_dev)))
        pinned = m.admit(first, fd); m.verify(first, fd, pinned)
        check('actual ext4 admission and current identity succeed', pinned[:4] == live)
        refuse('different real named directory refuses', lambda: probe.query(second, fd), 'ERRNO_18')
        refuse('named symlink is not followed', lambda: probe.query(WORK / 'alias', fd), 'ERRNO_20')
        refuse('missing real pathname refuses', lambda: probe.query(WORK / 'missing', fd), 'ERRNO_2')
        refuse('invalid descriptor refuses', lambda: probe.query(first, -1), 'INVALID_MOUNT_QUERY')
        refuse('boolean descriptor refuses', lambda: probe.query(first, True), 'INVALID_MOUNT_QUERY')
        refuse('unknown selector refuses', lambda: probe.query(first, fd, 1), 'INVALID_MOUNT_QUERY')
    finally:
        os.close(fd)
    refuse('closed real descriptor refuses', lambda: probe.query(first, fd), 'ERRNO_9')
    identity = '93939393939393939393939393939393'
    anchor = bd.create_image(WORK / 'image', identity, 1)
    (WORK / 'image-anchor.json').write_text(json.dumps(anchor, sort_keys=True) + '\n')
    image = bd.FixedBlockImage(WORK / 'image', identity, 1, expected_objects=anchor['objects'])
    try:
        with patch.object(m, 'query', wraps=m.query) as query, patch.object(m, 'inventory', side_effect=AssertionError('inventory in operation')):
            image.read(0, 0, 16); image.write(0, 0, b'A' * 16); image.erase(0); image.sync()
            check('read write erase sync each query current mount without rereading inventory', query.call_count == 4)
        with patch.object(m, 'query', side_effect=m.MountError('MOUNT_CHANGED')) as query, patch.object(bd.os, 'fsync') as sync:
            refuse('query failure refuses actual sync', image.sync, 'MOUNT_CHANGED', bd.ImageError)
            check('refused sync performed no fsync', not sync.called)
            refuse('mount uncertainty poisons the owner', image.sync, 'POISONED', bd.ImageError)
            check('poisoned owner does not retry mount query', query.call_count == 1)
    finally:
        image.close()
    report = dict(status='passed', checks=CHECKS, actualMountChanges=False,
                  actualUnprivilegedQueries=True, pinnedIdentity=list(live))
    with (WORK / 'checks.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
