"""Linux cooperative single-writer lease for an existing manipulation-run root.

The persistent lock inode is never truncated or removed. This protects cooperating
writers, not malicious directory replacement, kernel failures, or ignored leases.
Root parents are trusted; the final root component must not be a symlink.
"""

import os
from pathlib import Path
import stat
import sys

if sys.platform == "linux":
    import fcntl
else:
    fcntl = None


def _existing_root(root: str | Path) -> Path:
    path = Path(root)
    if path.is_symlink():
        raise RuntimeError("run root must not be a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RuntimeError("run root must be an existing directory")
    return resolved


class ManipulationRunLock:
    """Own one process-local lease; acquire before opening any writer state."""

    _NAME = ".manipulation-writer.lock"

    def __init__(self, root: Path, fd: int):
        self._root = root
        self._fd = fd
        self._pid = os.getpid()
        self._acquired = False
        info = os.fstat(fd)
        self._inode = (info.st_dev, info.st_ino)

    @classmethod
    def acquire(cls, existing_root: str | Path) -> "ManipulationRunLock":
        """Fail promptly if unsupported or contended; never create the root."""
        if sys.platform != "linux":
            raise RuntimeError("manipulation writer locks require Linux")
        root = _existing_root(existing_root)
        fd = os.open(
            root / cls._NAME,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            os.set_inheritable(fd, False)
            lease = cls(root, fd)
            lease._assert_identity()
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            lease._assert_identity()
            lease._acquired = True
            return lease
        except BaseException:
            os.close(fd)
            raise

    def _assert_identity(self) -> None:
        descriptor = os.fstat(self._fd)
        pathname = (self._root / self._NAME).lstat()
        if not stat.S_ISREG(descriptor.st_mode) or not stat.S_ISREG(pathname.st_mode):
            raise RuntimeError("lock must be a regular file")
        if (descriptor.st_dev, descriptor.st_ino) != self._inode or (
            pathname.st_dev,
            pathname.st_ino,
        ) != self._inode:
            raise RuntimeError("lock file identity changed")

    def assert_held(self, existing_root: str | Path) -> None:
        """Reject closed, inherited, wrong-root, or replaced-path leases."""
        if self._fd is None:
            raise RuntimeError("writer lock lease is closed")
        if os.getpid() != self._pid:
            raise RuntimeError("writer lock lease belongs to another process")
        if not self._acquired:
            raise RuntimeError("writer lock lease has not been acquired")
        if _existing_root(existing_root) != self._root:
            raise RuntimeError("writer lock lease belongs to another root")
        self._assert_identity()

    def close(self) -> None:
        """Close only this descriptor, including in a fork child; never LOCK_UN."""
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)

    def __enter__(self) -> "ManipulationRunLock":
        try:
            self.assert_held(self._root)
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
