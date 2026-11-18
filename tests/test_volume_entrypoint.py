"""Focused safety tests for the Docker volume bootstrap helpers."""

import importlib.util
import os
from pathlib import Path

import pytest


ENTRYPOINT_PATH = (
    Path(__file__).resolve().parents[1] / "docker" / "volume-entrypoint.py"
)
SPEC = importlib.util.spec_from_file_location("volume_entrypoint", ENTRYPOINT_PATH)
assert SPEC is not None and SPEC.loader is not None
volume_entrypoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(volume_entrypoint)


def test_mountinfo_requires_an_exact_mountpoint_and_decodes_escapes():
    mountinfo = (
        "41 30 0:38 / /data rw,relatime - ext4 /dev/vdb rw\n"
        "42 30 0:39 / /mnt/volume\\040space rw,relatime - ext4 /dev/vdc rw\n"
    )

    assert volume_entrypoint.mountinfo_contains(mountinfo, "/data")
    assert volume_entrypoint.mountinfo_contains(mountinfo, "/mnt/volume space")
    assert not volume_entrypoint.mountinfo_contains(mountinfo, "/data/child")
    assert not volume_entrypoint.mountinfo_contains(mountinfo, "/not-data")


@pytest.mark.parametrize(
    "name",
    [
        "knowledge.db",
        "knowledge.db-journal",
        "knowledge.db-wal",
        "knowledge.db-shm",
        "knowledge-local.db",
        "knowledge-local.db-journal",
        "knowledge-local.db-wal",
        "knowledge-local.db-shm",
    ],
)
def test_only_configured_database_files_and_sqlite_sidecars_are_managed(name):
    assert volume_entrypoint.is_sqlite_artifact(name)


@pytest.mark.parametrize(
    "name",
    ["other.db", "knowledge.db.backup", "knowledge-local.db.old", "unrelated.txt"],
)
def test_unrelated_files_are_not_managed(name):
    assert not volume_entrypoint.is_sqlite_artifact(name)


def test_database_paths_must_remain_under_the_volume():
    volume_entrypoint.verify_database_paths(
        {
            "DATABASE_PATH": "/data/knowledge.db",
            "LOCAL_DATABASE_PATH": "/data/knowledge-local.db",
        }
    )

    with pytest.raises(volume_entrypoint.BootstrapError, match="DATABASE_PATH"):
        volume_entrypoint.verify_database_paths(
            {
                "DATABASE_PATH": "/app/data/knowledge.db",
                "LOCAL_DATABASE_PATH": "/data/knowledge-local.db",
            }
        )


@pytest.mark.skipif(os.name != "posix", reason="dir-fd and O_NOFOLLOW checks are Linux-specific")
def test_managed_file_scan_ignores_unrelated_files(tmp_path):
    (tmp_path / "knowledge.db").write_bytes(b"sqlite")
    (tmp_path / "unrelated.db").write_bytes(b"leave untouched")
    directory_fd = os.open(
        tmp_path,
        os.O_RDONLY | volume_entrypoint.O_DIRECTORY | volume_entrypoint.O_NOFOLLOW,
    )
    try:
        files = volume_entrypoint._open_managed_files(directory_fd)
        try:
            assert [name for name, _ in files] == ["knowledge.db"]
        finally:
            for _, file_fd in files:
                os.close(file_fd)
    finally:
        os.close(directory_fd)


@pytest.mark.skipif(os.name != "posix", reason="symlink checks are Linux-specific")
def test_managed_file_scan_rejects_a_symlink(tmp_path):
    target = tmp_path / "unrelated.db"
    target.write_bytes(b"leave untouched")
    (tmp_path / "knowledge.db").symlink_to(target)
    directory_fd = os.open(
        tmp_path,
        os.O_RDONLY | volume_entrypoint.O_DIRECTORY | volume_entrypoint.O_NOFOLLOW,
    )
    try:
        with pytest.raises(volume_entrypoint.BootstrapError, match="symlink"):
            volume_entrypoint._open_managed_files(directory_fd)
    finally:
        os.close(directory_fd)
