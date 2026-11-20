"""Bounded Linux pathname-socket RPC; Unix users, not agent Sessions, are principals."""
from __future__ import annotations

import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
import threading
import time
import uuid

from .contracts import ContractError, MAX_BYTES, canonical, identifier, parse_json
from .api_contracts import ResponseError
from .journal import Context, JournalError

PROTOCOL = 'hctl.local/0.1'
MAX_CONNECTIONS = 16
IO_TIMEOUT = 2.0
_CREDENTIALS = struct.Struct('iII')


class IpcError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _code(error: Exception) -> str:
    if isinstance(error, ResponseError):
        return 'INVALID_RESPONSE'
    if isinstance(error, (IpcError, JournalError)):
        return error.code if re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', error.code) else 'INTERNAL_ERROR'
    if isinstance(error, ContractError):
        return 'INVALID_REQUEST'
    return 'INTERNAL_ERROR'


def _directory(path: Path) -> tuple[Path, int]:
    """Hold the private directory open, so later operations use the inspected inode."""
    if sys.platform != 'linux' or not hasattr(socket, 'SO_PEERCRED'):
        raise IpcError('UNSUPPORTED_PLATFORM')
    path = Path(os.path.abspath(path))
    if path.parent.resolve(strict=True) != path.parent:
        raise IpcError('UNSAFE_SOCKET_PATH')
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        os.close(fd)
        raise IpcError('UNSAFE_SOCKET_DIRECTORY')
    return path, fd


def _address(fd: int, name: str) -> str:
    # Linux resolves this pathname through the directory descriptor, including
    # after an ancestor is renamed. No abstract namespace or TCP fallback.
    return f'/proc/self/fd/{fd}/{name}'


def _peer_uid(connection: socket.socket) -> int:
    data = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _CREDENTIALS.size)
    return _CREDENTIALS.unpack(data)[1]


def _remaining(connection: socket.socket, deadline: float) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('socket deadline')
    connection.settimeout(remaining)


def _receive(connection: socket.socket, deadline: float) -> bytes:
    data = bytearray()
    while True:
        _remaining(connection, deadline)
        chunk = connection.recv(min(4096, MAX_BYTES + 1 - len(data)))
        if not chunk:
            raise IpcError('TRUNCATED_FRAME')
        data.extend(chunk)
        if b'\n' in data:
            body, trailing = data.split(b'\n', 1)
            if trailing:
                raise IpcError('MULTIPLE_FRAMES')
            return bytes(body)
        if len(data) > MAX_BYTES:
            raise IpcError('FRAME_TOO_LARGE')


def _send(connection: socket.socket, value, deadline: float) -> None:
    encoded = canonical(value)
    _remaining(connection, deadline)
    connection.sendall(encoded + b'\n')


def _request(value) -> tuple[str, str, dict]:
    if type(value) is not dict or set(value) != {'protocol', 'requestId', 'method', 'params'}:
        raise ContractError('local request fields')
    if value['protocol'] != PROTOCOL or type(value['params']) is not dict:
        raise ContractError('local request protocol or params')
    identifier(value['requestId'], 'request id')
    identifier(value['method'], 'method')
    return value['requestId'], value['method'], value['params']


class Server:
    """Serve one bounded request per connection against bounded runtime methods.

    The caller owns runtime.start/close. close() drains handlers before returning;
    a socket deadline cannot interrupt a blocking in-process runtime method.
    """
    def __init__(self, runtime, path: Path):
        self.runtime = runtime
        self.path, self._directory_fd = _directory(path)
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._stop = threading.Event()
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        self._lock = threading.Lock()
        self._workers: dict[threading.Thread, socket.socket] = {}
        self._inode = None
        self._closed = False
        try:
            try:
                os.stat(self.path.name, dir_fd=self._directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass  # A fresh pathname is required; stale sockets are never removed here.
            else:
                raise IpcError('SOCKET_PATH_EXISTS')
            self._socket.bind(_address(self._directory_fd, self.path.name))
            info = os.stat(self.path.name, dir_fd=self._directory_fd, follow_symlinks=False)
            self._inode = (info.st_dev, info.st_ino)
            os.chmod(self.path.name, 0o600, dir_fd=self._directory_fd, follow_symlinks=False)
            self._socket.listen(MAX_CONNECTIONS)
            self._socket.settimeout(0.2)
        except BaseException:
            self.close()
            raise

    def stop(self) -> None:
        self._stop.set()

    def serve_forever(self) -> None:
        while not self._stop.is_set():
            if not self._slots.acquire(timeout=0.2):
                continue
            try:
                connection, _ = self._socket.accept()
            except TimeoutError:
                self._slots.release()
                continue
            except OSError:
                self._slots.release()
                if self._stop.is_set():
                    return
                raise
            with self._lock:
                if self._stop.is_set():
                    connection.close()
                    self._slots.release()
                    return
                worker = threading.Thread(target=self._handle, args=(connection,), name='hctl-rpc')
                self._workers[worker] = connection
                try:
                    worker.start()
                except BaseException:
                    del self._workers[worker]
                    connection.close()
                    self._slots.release()
                    raise

    def _handle(self, connection: socket.socket) -> None:
        deadline = time.monotonic() + IO_TIMEOUT
        request_id = None
        try:
            try:
                context = Context(f'posix:{_peer_uid(connection)}', self.runtime.deployment)
                value = parse_json(_receive(connection, deadline))
                # Echo only a separately validated id, even if other fields fail.
                if type(value) is dict and type(value.get('requestId')) is str:
                    identifier(value['requestId'])
                    request_id = value['requestId']
                request_id, method, params = _request(value)
                _remaining(connection, deadline)
                result = self.runtime.request(context, method, params)
                response = {'protocol': PROTOCOL, 'requestId': request_id, 'result': result}
                try:
                    canonical(response)
                except ContractError:
                    raise IpcError('RESPONSE_TOO_LARGE') from None
            except Exception as error:
                response = {'protocol': PROTOCOL, 'requestId': request_id, 'error': {'code': _code(error)}}
            _send(connection, response, deadline)
        except (OSError, TimeoutError, IpcError):
            pass  # No reply can be promised after disconnect/deadline; never resubmit work.
        finally:
            connection.close()
            with self._lock:
                self._workers.pop(threading.current_thread(), None)
            self._slots.release()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.stop()
        self._socket.close()
        with self._lock:
            workers = list(self._workers.items())
        for _, connection in workers:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # Already disconnected; joining below still owns handler settlement.
        for worker, _ in workers:
            worker.join()
        try:
            if self._inode is not None:
                try:
                    info = os.stat(self.path.name, dir_fd=self._directory_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass  # An owner may have removed the socket; never recreate it during cleanup.
                else:
                    if (info.st_dev, info.st_ino) == self._inode:
                        os.unlink(self.path.name, dir_fd=self._directory_fd)
        finally:
            os.close(self._directory_fd)


def call(path: Path, method: str, params: dict):
    """Call once; transport failures never cause an automatic retry."""
    request_id = uuid.uuid4().hex
    request = {'protocol': PROTOCOL, 'requestId': request_id, 'method': method, 'params': params}
    _request(request)
    canonical(request)
    directory_fd = None
    try:
        path, directory_fd = _directory(path)
        info = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise IpcError('UNSAFE_SOCKET_PATH')
        deadline = time.monotonic() + IO_TIMEOUT
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            _remaining(connection, deadline)
            connection.connect(_address(directory_fd, path.name))
            if _peer_uid(connection) != info.st_uid:
                raise IpcError('SERVER_IDENTITY_MISMATCH')
            _send(connection, request, deadline)
            try:
                response = parse_json(_receive(connection, deadline))
            except ContractError:
                raise IpcError('INVALID_RESPONSE') from None
        if (type(response) is not dict or response.get('protocol') != PROTOCOL or
                response.get('requestId') != request_id):
            raise IpcError('INVALID_RESPONSE')
        if set(response) == {'protocol', 'requestId', 'result'}:
            return response['result']
        if set(response) == {'protocol', 'requestId', 'error'}:
            error = response['error']
            if type(error) is dict and set(error) == {'code'} and type(error['code']) is str:
                if re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', error['code']):
                    raise IpcError(error['code'])
        raise IpcError('INVALID_RESPONSE')
    except TimeoutError:
        raise IpcError('TRANSPORT_TIMEOUT') from None
    except OSError:
        raise IpcError('TRANSPORT_ERROR') from None
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
