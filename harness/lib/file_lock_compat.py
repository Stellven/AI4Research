"""Small ``fcntl.flock`` compatibility surface for Solar runtime lock files."""
from __future__ import annotations

try:  # POSIX keeps the native semantics.
    import fcntl as _fcntl
except ModuleNotFoundError:  # pragma: no cover - exercised on Windows
    _fcntl = None


if _fcntl is not None:
    LOCK_EX = _fcntl.LOCK_EX
    LOCK_NB = _fcntl.LOCK_NB
    LOCK_UN = _fcntl.LOCK_UN

    def flock(file_object, operation: int) -> None:
        _fcntl.flock(file_object, operation)

else:  # Windows: lock one byte in the dedicated lock file.
    import errno
    import msvcrt
    import os

    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 8

    def _descriptor(file_or_fd) -> int:
        if isinstance(file_or_fd, int):
            return file_or_fd
        return int(file_or_fd.fileno())

    def _prepare_lock_byte(fd: int) -> None:
        """Ensure byte zero exists and position the descriptor on that byte."""
        if os.fstat(fd).st_size == 0:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.write(fd, b"\0") != 1:
                raise OSError("unable to prepare Windows lock byte")
            os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)

    def flock(file_or_fd, operation: int) -> None:
        fd = _descriptor(file_or_fd)
        _prepare_lock_byte(fd)
        if operation & LOCK_UN:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            return
        mode = msvcrt.LK_NBLCK if operation & LOCK_NB else msvcrt.LK_LOCK
        try:
            msvcrt.locking(fd, mode, 1)
        except OSError as exc:
            contention = exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
            contention = contention or getattr(exc, "winerror", None) == 33
            if operation & LOCK_NB and contention:
                raise BlockingIOError(errno.EAGAIN, "lock is already held") from exc
            raise
