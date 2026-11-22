import errno
import os

import pytest

from folder_sync import synchronize_folders
from folder_sync.cli import main
from .conftest import tree, write


@pytest.mark.parametrize("parallel", [False, True])
def test_destination_becomes_copy_of_source(populated, parallel):
    source, destination = populated
    report = synchronize_folders(source, destination, parallel=parallel, verbose=False)
    assert report["ok"]
    assert tree(source) == tree(destination)
    assert (destination / "empty_dir").is_dir()
    assert not (destination / "old_dir").exists()


def test_sequential_and_parallel_give_same_result(populated, tmp_path):
    source, destination = populated
    other = tmp_path / "dst2"
    synchronize_folders(source, destination, parallel=False, verbose=False)
    synchronize_folders(source, other, parallel=True, verbose=False)
    assert tree(destination) == tree(other)


@pytest.mark.parametrize("parallel", [False, True])
def test_idempotent(populated, parallel):
    source, destination = populated
    synchronize_folders(source, destination, parallel=parallel, verbose=False)
    report = synchronize_folders(source, destination, parallel=parallel, verbose=False)
    plan = report["plan"]
    assert not (plan["copy"] or plan["update"] or plan["delete"])
    assert len(plan["unchanged"]) == 4


def test_modified_in_source_is_updated(populated):
    source, destination = populated
    synchronize_folders(source, destination, verbose=False)
    write(source / "a.txt", b"nuovo contenuto", mtime=os.stat(source / "a.txt").st_mtime + 50)
    synchronize_folders(source, destination, verbose=False)
    assert (destination / "a.txt").read_bytes() == b"nuovo contenuto"


def test_file_modified_in_backup_is_restored(populated):
    source, destination = populated
    synchronize_folders(source, destination, verbose=False)
    write(destination / "a.txt", b"manomesso", mtime=os.stat(source / "a.txt").st_mtime + 500)
    synchronize_folders(source, destination, verbose=False)
    assert (destination / "a.txt").read_bytes() == b"alpha"


def test_newer_mode_keeps_backup_modification(populated):
    source, destination = populated
    synchronize_folders(source, destination, verbose=False)
    write(destination / "a.txt", b"manomesso", mtime=os.stat(source / "a.txt").st_mtime + 500)
    synchronize_folders(source, destination, comparison="newer", verbose=False)
    assert (destination / "a.txt").read_bytes() == b"manomesso"


def test_checksum_mode_detects_same_size_content_change(populated):
    source, destination = populated
    synchronize_folders(source, destination, verbose=False)
    mtime = os.stat(source / "a.txt").st_mtime
    write(destination / "a.txt", b"ALPHA", mtime=mtime)  # stessa dimensione, stessa data
    synchronize_folders(source, destination, comparison="checksum", verbose=False)
    assert (destination / "a.txt").read_bytes() == b"alpha"


def test_dry_run_changes_nothing(populated):
    source, destination = populated
    before = tree(destination)
    report = synchronize_folders(source, destination, dry_run=True, verbose=False)
    assert tree(destination) == before
    assert report["plan"]["copy"]


def test_copy_failure_is_reported(populated, monkeypatch):
    source, destination = populated

    def boom(*args, **kwargs):
        raise PermissionError("negato")

    monkeypatch.setattr("folder_sync.operations.shutil.copy2", boom)
    report = synchronize_folders(source, destination, verbose=False)
    assert not report["ok"]
    assert report["failed_operations"]


def test_unexpected_rmdir_error_is_reported(populated, monkeypatch):
    source, destination = populated

    def boom(path):
        raise OSError(errno.EACCES, "permesso negato")

    monkeypatch.setattr("folder_sync.operations.os.rmdir", boom)
    report = synchronize_folders(source, destination, verbose=False)
    assert any(r["action"] == "rmdir" for r in report["failed_operations"])


def test_not_empty_rmdir_is_ignored(populated, monkeypatch):
    source, destination = populated

    def not_empty(path):
        raise OSError(errno.ENOTEMPTY, "non vuota")

    monkeypatch.setattr("folder_sync.operations.os.rmdir", not_empty)
    report = synchronize_folders(source, destination, verbose=False)
    assert not any(r["action"] == "rmdir" for r in report["failed_operations"])


def test_deletions_skipped_when_source_scan_has_errors(populated, monkeypatch):
    source, destination = populated
    import folder_sync.sync as sync_module

    real = sync_module.scan_folder_sequential

    def flaky(folder, compute_hash=False):
        index, dirs, errors = real(folder, compute_hash)
        if str(folder) == str(source.resolve()):
            errors = errors + [{"file": "x", "error": "illeggibile"}]
        return index, dirs, errors

    monkeypatch.setattr(sync_module, "scan_folder_sequential", flaky)
    report = synchronize_folders(source, destination, verbose=False)
    assert report["deletions_skipped"] and not report["ok"]
    assert (destination / "old_dir" / "obsolete.txt").exists()


def test_cli_exit_codes(populated, tmp_path):
    source, destination = populated
    assert main([str(source), str(destination), "--quiet"]) == 0
    assert main([str(tmp_path / "missing"), str(destination), "--quiet"]) == 2
    assert main([str(source), str(destination), "--parallel", "--quiet"]) == 0
