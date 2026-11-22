"""Fixture condivise dai test."""

import os
from pathlib import Path

import pytest


def write(path: Path, content: bytes = b"x", mtime: float = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def tree(folder: Path):
    """File (con contenuto) e cartelle di un albero, per i confronti."""
    files = {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    dirs = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_dir()}
    return files, dirs


@pytest.fixture
def folders(tmp_path):
    source = tmp_path / "src"
    destination = tmp_path / "dst"
    source.mkdir()
    destination.mkdir()
    return source, destination


@pytest.fixture
def populated(folders):
    """Sorgente con file, sottocartelle e una cartella vuota; destinazione con un file obsoleto."""
    source, destination = folders
    write(source / "a.txt", b"alpha")
    write(source / "sub" / "b.txt", b"beta")
    write(source / "sub" / "deep" / "c.txt", b"gamma")
    write(source / "other" / "d.txt", b"delta")
    (source / "empty_dir").mkdir()
    write(destination / "old_dir" / "obsolete.txt", b"old")
    return source, destination
