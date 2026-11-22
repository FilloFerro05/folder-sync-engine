import pytest

from folder_sync.planner import build_sync_plan, needs_update


def f(size=1, mtime=100, sha="h"):
    return {"size": size, "modified_time": mtime, "sha256": sha}


def test_newer_ignores_older_source():
    assert needs_update(f(mtime=200), f(mtime=100), "newer")
    assert not needs_update(f(mtime=100), f(mtime=200), "newer")


def test_any_difference_restores_file_modified_in_backup():
    # caso segnalato dal professore: file modificato direttamente nel backup
    assert needs_update(f(mtime=100), f(mtime=200), "any_difference")
    assert needs_update(f(size=1), f(size=2), "any_difference")
    assert not needs_update(f(), f(), "any_difference")


def test_tolerance():
    assert not needs_update(f(mtime=100), f(mtime=101), "any_difference", mtime_tolerance_ns=5)


def test_checksum():
    assert needs_update(f(sha="a"), f(sha="b"), "checksum")
    assert not needs_update(f(mtime=1, sha="a"), f(mtime=9, sha="a"), "checksum")


def test_plan_categories_and_dirs():
    src = {"new.txt": f(), "same.txt": f(), "mod.txt": f(size=2)}
    dst = {"same.txt": f(), "mod.txt": f(size=1), "gone.txt": f()}
    plan = build_sync_plan(src, dst, ["a", "a/b", "empty"], ["old", "old/sub"])
    assert plan["copy"] == ["new.txt"]
    assert plan["update"] == ["mod.txt"]
    assert plan["delete"] == ["gone.txt"]
    assert plan["unchanged"] == ["same.txt"]
    assert plan["create_dirs"].index("a") < plan["create_dirs"].index("a/b")
    assert "empty" in plan["create_dirs"]
    assert plan["remove_dirs"].index("old/sub") < plan["remove_dirs"].index("old")


def test_invalid_mode():
    with pytest.raises(ValueError):
        build_sync_plan({}, {}, comparison="boh")
