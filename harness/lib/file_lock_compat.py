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
    import msvcrt

    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 8

    def flock(file_object, operation: int) -> None:
        file_object.seek(0, 2)
        if file_object.tell() == 0:
            file_object.write("\0")
            file_object.flush()
        file_object.seek(0)
        if operation & LOCK_UN:
            try:
                msvcrt.locking(file_object.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            return
        mode = msvcrt.LK_NBLCK if operation & LOCK_NB else msvcrt.LK_LOCK
        try:
            msvcrt.locking(file_object.fileno(), mode, 1)
        except OSError as exc:
            if operation & LOCK_NB:
                raise BlockingIOError(str(exc)) from exc
            raise
