import hashlib
import os

import pytest

from folder_sync.scanner import (
    hash_file, scan_folder_multiprocessing, scan_folder_sequential, split_into_chunks,
)


def test_split_into_chunks():
    chunks = split_into_chunks(list(range(7)), 3)
    assert sum(chunks, []) == list(range(7))
    assert len(chunks) == 3


def test_hash_file(tmp_path):
    f = tmp_path / "f"
    f.write_bytes(b"hello")
    assert hash_file(f) == hashlib.sha256(b"hello").hexdigest()


def test_sequential_scan_content(populated):
    source, _ = populated
    index, dirs, errors = scan_folder_sequential(source)
    assert set(index) == {"a.txt", "sub/b.txt", "sub/deep/c.txt", "other/d.txt"}
    assert {"sub", "sub/deep", "other", "empty_dir"} <= set(dirs)
    assert errors == []
    assert index["a.txt"]["size"] == 5 and index["a.txt"]["sha256"] is None


def test_parallel_scan_equals_sequential(populated):
    source, _ = populated
    seq = scan_folder_sequential(source, compute_hash=True)
    par = scan_folder_multiprocessing(source, 2, compute_hash=True)
    assert seq[0] == par[0]
    assert sorted(seq[1]) == sorted(par[1])
    assert seq[2] == par[2] == []


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="solo Unix")
def test_non_regular_files_skipped(tmp_path):
    (tmp_path / "f.txt").write_text("x")
    os.mkfifo(tmp_path / "pipe")
    index, _, _ = scan_folder_sequential(tmp_path)
    assert set(index) == {"f.txt"}
