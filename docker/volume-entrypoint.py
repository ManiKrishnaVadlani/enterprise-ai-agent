"""Validate and prepare the persistent data volume before starting the API."""

from __future__ import annotations

import errno
import os
import re
import secrets
import stat
import sys
from collections.abc import Mapping
from pathlib import Path


DATA_PATH = "/data"
APP_UID = 10001
APP_GID = 10001
DATABASE_FILES = ("knowledge.db", "knowledge-local.db")
SQLITE_SUFFIXES = ("", "-journal", "-wal", "-shm")
GOSU_PATH = "/usr/sbin/gosu"

O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


class BootstrapError(RuntimeError):
    """Raised when volume validation or privilege setup cannot be completed."""


def is_sqlite_artifact(name: str) -> bool:
    """Match only the configured database files and their SQLite sidecars."""
    return any(
        name == database + suffix
        for database in DATABASE_FILES
        for suffix in SQLITE_SUFFIXES
    )


def mountinfo_contains(mountinfo: str, mount_path: str) -> bool:
    """Return whether mountinfo contains an exact mount point, decoding escapes."""
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) < 6:
            continue
        encoded_path = fields[4]
        decoded_path = re.sub(
            r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), encoded_path
        )
        if decoded_path == mount_path:
            return True
    return False


def _fail(message: str) -> None:
    raise BootstrapError(message)


def verify_database_paths(environment: Mapping[str, str] = os.environ) -> None:
    expected = {
        "DATABASE_PATH": "/data/knowledge.db",
        "LOCAL_DATABASE_PATH": "/data/knowledge-local.db",
    }
    for variable, path in expected.items():
        if environment.get(variable) != path:
            _fail(f"{variable} must be set to {path!r} so SQLite stays on the volume.")


def _open_volume() -> int:
    railway_mount = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if railway_mount and railway_mount != DATA_PATH:
        _fail(
            "RAILWAY_VOLUME_MOUNT_PATH must be /data for this service; "
            f"received {railway_mount!r}."
        )

    if not O_NOFOLLOW or not O_DIRECTORY:
        _fail("This container requires Linux O_NOFOLLOW and O_DIRECTORY support.")

    try:
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError as error:
        raise BootstrapError("Could not read /proc/self/mountinfo.") from error
    if not mountinfo_contains(mountinfo, DATA_PATH):
        _fail("/data is not a mounted volume; refusing to start without persistent storage.")

    try:
        volume_fd = os.open(
            DATA_PATH, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
        )
    except OSError as error:
        raise BootstrapError("/data must exist as a real directory, not a symlink.") from error

    if not stat.S_ISDIR(os.fstat(volume_fd).st_mode):
        os.close(volume_fd)
        _fail("/data is not a directory.")
    return volume_fd


def _open_managed_files(volume_fd: int) -> list[tuple[str, int]]:
    """Open only known SQLite paths without following links or accepting hardlinks."""
    opened: list[tuple[str, int]] = []
    flags = os.O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC
    try:
        for name in os.listdir(volume_fd):
            if not is_sqlite_artifact(name):
                continue
            try:
                path_info = os.stat(name, dir_fd=volume_fd, follow_symlinks=False)
            except OSError as error:
                raise BootstrapError(f"Could not inspect /data/{name} safely.") from error
            if stat.S_ISLNK(path_info.st_mode):
                _fail(f"Refusing unexpected symlink at /data/{name}.")
            if not stat.S_ISREG(path_info.st_mode) or path_info.st_nlink != 1:
                _fail(f"Refusing non-regular or hard-linked SQLite path /data/{name}.")
            try:
                file_fd = os.open(name, flags, dir_fd=volume_fd)
            except OSError as error:
                if error.errno in {errno.ELOOP, errno.EMLINK}:
                    _fail(f"Refusing unexpected symlink at /data/{name}.")
                raise BootstrapError(f"Could not safely open /data/{name}.") from error

            info = os.fstat(file_fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
            ):
                os.close(file_fd)
                _fail(f"Refusing non-regular or hard-linked SQLite path /data/{name}.")
            opened.append((name, file_fd))
        return opened
    except Exception:
        for _, file_fd in opened:
            os.close(file_fd)
        raise


def _set_owner_and_modes(volume_fd: int, files: list[tuple[str, int]]) -> None:
    try:
        os.fchown(volume_fd, APP_UID, APP_GID)
        os.fchmod(volume_fd, 0o700)
        for _, file_fd in files:
            os.fchown(file_fd, APP_UID, APP_GID)
            os.fchmod(file_fd, 0o600)
    except OSError as error:
        raise BootstrapError(
            "Could not assign /data and its SQLite files to UID/GID 10001. "
            "When using Railway, set RAILWAY_RUN_UID=0 only with this "
            "privilege-dropping entrypoint."
        ) from error


def _verify_app_user_access(volume_fd: int, files: list[tuple[str, int]]) -> None:
    directory = os.fstat(volume_fd)
    if directory.st_uid != APP_UID or directory.st_gid != APP_GID:
        _fail("/data is not owned by appuser (UID/GID 10001).")
    if not os.access(DATA_PATH, os.W_OK | os.X_OK, effective_ids=True):
        _fail("appuser cannot write to /data.")

    for name, file_fd in files:
        info = os.fstat(file_fd)
        if info.st_uid != APP_UID or info.st_gid != APP_GID:
            _fail(f"/data/{name} is not owned by appuser (UID/GID 10001).")
        try:
            writable_fd = os.open(
                name, os.O_RDWR | O_NOFOLLOW | O_CLOEXEC, dir_fd=volume_fd
            )
        except OSError as error:
            raise BootstrapError(f"appuser cannot write to /data/{name}.") from error
        else:
            os.close(writable_fd)

    probe_name = f".volume-write-check-{os.getpid()}-{secrets.token_hex(6)}"
    try:
        probe_fd = os.open(
            probe_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW | O_CLOEXEC,
            0o600,
            dir_fd=volume_fd,
        )
        os.close(probe_fd)
        os.unlink(probe_name, dir_fd=volume_fd)
    except OSError as error:
        try:
            os.unlink(probe_name, dir_fd=volume_fd)
        except OSError:
            pass
        raise BootstrapError("appuser cannot create and remove files in /data.") from error


def _run_as_appuser(command: list[str]) -> None:
    if not os.path.isfile(GOSU_PATH) or not os.access(GOSU_PATH, os.X_OK):
        _fail("gosu is missing or not executable; refusing to start as root.")
    script = os.path.abspath(__file__)
    argv = [
        GOSU_PATH,
        f"{APP_UID}:{APP_GID}",
        sys.executable,
        "-I",
        script,
        "--after-drop",
        "--",
        *command,
    ]
    os.execv(GOSU_PATH, argv)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    after_drop = False
    if args and args[0] == "--after-drop":
        after_drop = True
        args = args[1:]
        if not args or args.pop(0) != "--":
            _fail("Invalid internal privilege-drop invocation.")
    if not args:
        _fail("No application command was supplied to the volume entrypoint.")

    try:
        verify_database_paths()
        effective_uid = os.geteuid()
        effective_gid = os.getegid()
        if after_drop:
            if (effective_uid, effective_gid) != (APP_UID, APP_GID):
                _fail("gosu did not switch the process to UID/GID 10001.")
        elif effective_uid == 0:
            if os.environ.get("RAILWAY_RUN_UID") != "0":
                _fail("Root startup is allowed only with RAILWAY_RUN_UID=0.")
        elif (effective_uid, effective_gid) != (APP_UID, APP_GID):
            _fail(
                "The entrypoint must run as root for Railway setup or as appuser 10001."
            )

        volume_fd = _open_volume()
        files = _open_managed_files(volume_fd)
        try:
            if effective_uid == 0:
                _set_owner_and_modes(volume_fd, files)
                _run_as_appuser(args)
            _verify_app_user_access(volume_fd, files)
        finally:
            for _, file_fd in files:
                os.close(file_fd)
            os.close(volume_fd)

        os.execvp(args[0], args)
    except BootstrapError as error:
        print(f"volume-entrypoint: {error}", file=sys.stderr, flush=True)
        return 1
    except OSError as error:
        print(f"volume-entrypoint: startup failed: {error}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
