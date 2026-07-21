"""Audit-only network guard loaded by Python subprocesses through PYTHONPATH."""

from __future__ import annotations

import ipaddress
import socket


_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_create_connection = socket.create_connection


def _is_loopback_address(address: object) -> bool:
    if isinstance(address, str):
        return True  # Unix-domain socket path.
    if not isinstance(address, tuple) or not address:
        return True
    host = str(address[0]).strip("[]")
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guard(address: object) -> None:
    if not _is_loopback_address(address):
        raise OSError(f"QA_AUDIT_NETWORK_BLOCKED: non-loopback connection denied: {address!r}")


def guarded_connect(self: socket.socket, address: object):
    _guard(address)
    return _original_connect(self, address)


def guarded_connect_ex(self: socket.socket, address: object):
    _guard(address)
    return _original_connect_ex(self, address)


def guarded_create_connection(address: object, *args, **kwargs):
    _guard(address)
    return _original_create_connection(address, *args, **kwargs)


socket.socket.connect = guarded_connect
socket.socket.connect_ex = guarded_connect_ex
socket.create_connection = guarded_create_connection
