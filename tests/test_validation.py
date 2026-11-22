import pytest

from folder_sync.validation import validate_folders


def test_creates_destination(tmp_path):
    source = tmp_path / "s"
    source.mkdir()
    _, destination = validate_folders(source, tmp_path / "d")
    assert destination.is_dir()


def test_missing_source(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_folders(tmp_path / "nope", tmp_path / "d")


def test_source_is_file(tmp_path):
    f = tmp_path / "f"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        validate_folders(f, tmp_path / "d")


def test_destination_is_file(tmp_path):
    (tmp_path / "s").mkdir()
    f = tmp_path / "f"
    f.write_text("x")
    with pytest.raises(NotADirectoryError):
        validate_folders(tmp_path / "s", f)


def test_same_folder(tmp_path):
    with pytest.raises(ValueError):
        validate_folders(tmp_path, tmp_path)


def test_nested_folders(tmp_path):
    (tmp_path / "s" / "inner").mkdir(parents=True)
    with pytest.raises(ValueError):
        validate_folders(tmp_path / "s", tmp_path / "s" / "inner")
    with pytest.raises(ValueError):
        validate_folders(tmp_path / "s" / "inner", tmp_path / "s")
