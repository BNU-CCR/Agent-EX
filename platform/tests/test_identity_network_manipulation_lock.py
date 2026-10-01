"""MOCK syscall contract checks; Linux kernel acceptance is separate and skip-gated."""

import importlib
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


def lock_module():
    name = "agent_ex.identity_network.manipulation_lock"
    assert importlib.util.find_spec(name) is not None, "writer lock feature is missing"
    return importlib.import_module(name)


def test_native_unsupported_has_no_filesystem_mutation(tmp_path):
    module = lock_module()
    if sys.platform == "linux":
        pytest.skip("native unsupported-platform check")
    root = tmp_path / "absent"
    with pytest.raises(RuntimeError, match="Linux"):
        module.ManipulationRunLock.acquire(root)
    assert not root.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def mock_syscalls(monkeypatch):
    """MOCK only: real local files, simulated Linux open flags and flock."""
    module = lock_module()
    calls = SimpleNamespace(
        closed=[],
        flags=[],
        flock=[],
        pid=os.getpid(),
        fail=False,
        replaced=False,
        replace_after_flock=False,
        fail_inheritable=False,
    )
    original_lstat = Path.lstat

    def lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path.name == ".manipulation-writer.lock" and calls.replaced:
            return SimpleNamespace(
                st_mode=info.st_mode,
                st_dev=info.st_dev,
                st_ino=info.st_ino + 1,
            )
        return info

    def set_inheritable(fd, value):
        if calls.fail_inheritable:
            raise OSError("inheritable failed")
        os.set_inheritable(fd, value)

    def open_file(path, flags, mode):
        calls.flags.append((flags, mode))
        return os.open(path, os.O_RDWR | os.O_CREAT, mode)

    def close_file(fd):
        calls.closed.append(fd)
        os.close(fd)

    def flock(fd, flags):
        calls.flock.append((fd, flags))
        if calls.fail:
            raise BlockingIOError("contended")
        if calls.replace_after_flock:
            calls.replaced = True

    fake_os = SimpleNamespace(
        open=open_file,
        close=close_file,
        fstat=os.fstat,
        set_inheritable=set_inheritable,
        getpid=lambda: calls.pid,
        O_RDWR=2,
        O_CREAT=64,
        O_NOFOLLOW=131072,
        O_CLOEXEC=524288,
    )
    monkeypatch.setattr(module, "os", fake_os)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(module, "fcntl", SimpleNamespace(LOCK_EX=2, LOCK_NB=4, flock=flock))
    monkeypatch.setattr(Path, "lstat", lstat)
    return module.ManipulationRunLock, calls


def test_mock_context_flags_persistent_file_and_exception_cleanup(tmp_path, mock_syscalls):
    lock, calls = mock_syscalls
    path = tmp_path / ".manipulation-writer.lock"
    path.write_text("persistent contents", encoding="utf-8")
    with pytest.raises(ValueError, match="body"):
        with lock.acquire(tmp_path) as lease:
            lease.assert_held(tmp_path)
            assert not os.get_inheritable(lease._fd)
            raise ValueError("body")
    assert path.read_text(encoding="utf-8") == "persistent contents"
    assert calls.flags == [(2 | 64 | 131072 | 524288, 0o600)]
    assert [flags for _, flags in calls.flock] == [2 | 4]
    assert len(calls.closed) == 1
    lease.close()
    assert len(calls.closed) == 1
    with pytest.raises(RuntimeError, match="closed"):
        lease.__enter__()
    with pytest.raises(RuntimeError, match="closed"):
        lease.assert_held(tmp_path)


def test_mock_contention_closes_descriptor_without_removing_file(tmp_path, mock_syscalls):
    lock, calls = mock_syscalls
    calls.fail = True
    with pytest.raises(BlockingIOError):
        lock.acquire(tmp_path)
    assert len(calls.closed) == 1
    assert (tmp_path / ".manipulation-writer.lock").is_file()


def test_mock_failed_context_entry_closes_descriptor(tmp_path, mock_syscalls):
    lock, calls = mock_syscalls
    lease = lock.acquire(tmp_path)
    calls.replaced = True
    try:
        with pytest.raises(RuntimeError, match="identity"):
            with lease:
                pytest.fail("replaced lock must not enter the context")
        assert len(calls.closed) == 1
        assert (tmp_path / ".manipulation-writer.lock").is_file()
        lease.close()
        assert len(calls.closed) == 1
    finally:
        lease.close()


def test_mock_wrong_root_and_replaced_path(tmp_path, mock_syscalls):
    lock, calls = mock_syscalls
    other = tmp_path / "other"
    other.mkdir()
    with lock.acquire(tmp_path) as lease:
        with pytest.raises(RuntimeError, match="root"):
            lease.assert_held(other)
        calls.replaced = True
        with pytest.raises(RuntimeError, match="identity"):
            lease.assert_held(tmp_path)


@pytest.mark.parametrize("failure", ["replaced", "replace_after_flock", "fail_inheritable"])
def test_mock_acquisition_failure_closes_fd(tmp_path, mock_syscalls, failure):
    lock, calls = mock_syscalls
    setattr(calls, failure, True)
    with pytest.raises((RuntimeError, OSError)):
        lock.acquire(tmp_path)
    assert len(calls.closed) == 1
    assert (tmp_path / ".manipulation-writer.lock").is_file()
    if failure == "replaced":
        assert calls.flock == []


def test_mock_other_pid_cannot_use_but_close_only_closes_fd(tmp_path, mock_syscalls):
    lock, calls = mock_syscalls
    lease = lock.acquire(tmp_path)
    calls.pid += 1
    with pytest.raises(RuntimeError, match="process"):
        lease.assert_held(tmp_path)
    with pytest.raises(RuntimeError, match="process"):
        lease.__enter__()
    lease.close()
    lease.close()
    assert len(calls.closed) == 1
    assert [flags for _, flags in calls.flock] == [2 | 4]


def test_mock_requires_existing_directory(tmp_path, mock_syscalls):
    lock, calls = mock_syscalls
    with pytest.raises((FileNotFoundError, RuntimeError)):
        lock.acquire(tmp_path / "absent")
    regular = tmp_path / "file"
    regular.touch()
    with pytest.raises(RuntimeError, match="directory"):
        lock.acquire(regular)
    assert calls.flags == []


def test_mock_direct_construction_is_not_an_acquired_lease(tmp_path, mock_syscalls):
    lock, calls = mock_syscalls
    fd = os.open(tmp_path / ".manipulation-writer.lock", os.O_RDWR | os.O_CREAT, 0o600)
    lease = lock(tmp_path.resolve(), fd)
    try:
        with pytest.raises(RuntimeError, match="acquired"):
            lease.assert_held(tmp_path)
        with pytest.raises(RuntimeError, match="acquired"):
            lease.__enter__()
        assert calls.flock == []
    finally:
        lease.close()


LINUX_ONLY = pytest.mark.skipif(sys.platform != "linux", reason="Linux kernel acceptance only")


@LINUX_ONLY
def test_linux_rejects_root_and_lock_symlinks_and_nonregular(tmp_path):
    lock = lock_module().ManipulationRunLock
    root_link = tmp_path / "root-link"
    root_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        lock.acquire(root_link)
    path = tmp_path / ".manipulation-writer.lock"
    target = tmp_path / "target"
    target.touch()
    path.symlink_to(target)
    with pytest.raises((OSError, RuntimeError)):
        lock.acquire(tmp_path)
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(RuntimeError, match="regular"):
        lock.acquire(tmp_path)


@LINUX_ONLY
def test_linux_subprocess_contention_and_reacquire_after_death(tmp_path):
    lock = lock_module().ManipulationRunLock
    code = (
        "import sys,time; from agent_ex.identity_network.manipulation_lock "
        "import ManipulationRunLock; lease=ManipulationRunLock.acquire(sys.argv[1]); "
        "print('held',flush=True); time.sleep(60)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(tmp_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        import select

        readable, _, _ = select.select([process.stdout], [], [], 10)
        assert readable, "child did not acquire the lease within ten seconds"
        assert process.stdout.readline().strip() == "held"
        with pytest.raises(BlockingIOError):
            lock.acquire(tmp_path)
        process.kill()
        process.communicate(timeout=5)
        with lock.acquire(tmp_path) as lease:
            lease.assert_held(tmp_path)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
