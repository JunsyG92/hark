"""Outbound network guard: the engine may only talk to loopback.

Installed at startup. Any attempt to connect (or resolve a name) outside loopback raises
NetworkBlockedError and is counted, which makes "no outgoing network call" verifiable. The only
exceptions are explicit user actions wrapped in `allow_network()` (downloading a model).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

log = logging.getLogger(__name__)

_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost"}
_lock = threading.Lock()
_allow_depth = 0
_blocked: list[str] = []
_installed = False
_orig: dict[str, Any] = {}


class NetworkBlockedError(OSError):
    """Raised instead of making a non-loopback network call."""


def blocked_attempts() -> list[str]:
    with _lock:
        return list(_blocked)


@contextmanager
def allow_network() -> Iterator[None]:
    """Explicit, user-initiated network use (process-wide while active)."""
    global _allow_depth
    with _lock:
        _allow_depth += 1
    try:
        yield
    finally:
        with _lock:
            _allow_depth -= 1


def _is_loopback_host(host: object) -> bool:
    if host is None or host == "":
        return True  # wildcard bind / unspecified: not an outbound destination
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    if not isinstance(host, str):
        return False
    if host.lower() in _LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


def _check(target: str, ok: bool) -> None:
    if ok:
        return
    with _lock:
        if _allow_depth > 0:
            return
        _blocked.append(target)
    log.error("blocked outbound network access to %s", target)
    raise NetworkBlockedError(f"outbound network access blocked by Hark (target: {target})")


def install_guard() -> None:
    """Patch socket connect/resolve (idempotent)."""
    global _installed
    if _installed:
        return
    _installed = True
    _orig["connect"] = socket.socket.connect
    _orig["connect_ex"] = socket.socket.connect_ex
    _orig["getaddrinfo"] = socket.getaddrinfo

    def connect(self: socket.socket, address: Any) -> None:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _check(str(address), _is_loopback_host(address[0]))
        return _orig["connect"](self, address)  # type: ignore[no-any-return]

    def connect_ex(self: socket.socket, address: Any) -> int:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            _check(str(address), _is_loopback_host(address[0]))
        return _orig["connect_ex"](self, address)  # type: ignore[no-any-return]

    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        _check(str(host), _is_loopback_host(host))
        return _orig["getaddrinfo"](host, *args, **kwargs)

    socket.socket.connect = connect  # type: ignore[method-assign,assignment]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign,assignment]
    socket.getaddrinfo = getaddrinfo


def uninstall_guard() -> None:
    """Restore the original socket functions (tests only)."""
    global _installed
    if not _installed:
        return
    socket.socket.connect = _orig["connect"]  # type: ignore[method-assign]
    socket.socket.connect_ex = _orig["connect_ex"]  # type: ignore[method-assign]
    socket.getaddrinfo = _orig["getaddrinfo"]
    with _lock:
        _blocked.clear()
    _installed = False
