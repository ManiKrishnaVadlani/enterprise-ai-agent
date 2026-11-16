from contextlib import ExitStack
from pathlib import Path

import pytest

from contextlib_example import (
    delete_file_if_present,
    managed_document,
    read_document,
    read_multiple_documents,
)


def test_contextmanager_yield_separates_setup_from_use_and_cleanup():
    events = []

    result = read_document("handbook.pdf", events)

    assert result == "Reading handbook.pdf"
    assert events == [
        "open:handbook.pdf",
        "read:handbook.pdf",
        "close:handbook.pdf",
    ]


def test_contextmanager_cleanup_runs_and_exception_propagates():
    events = []

    with pytest.raises(ValueError, match="document is damaged"):
        with managed_document("handbook.pdf", events):
            raise ValueError("document is damaged")

    assert events == ["open:handbook.pdf", "close:handbook.pdf"]


def test_suppress_ignores_only_a_missing_file(tmp_path: Path):
    missing_file = tmp_path / "missing.txt"

    assert delete_file_if_present(missing_file) is False

    existing_file = tmp_path / "present.txt"
    existing_file.write_text("example", encoding="utf-8")
    assert delete_file_if_present(existing_file) is True
    assert existing_file.exists() is False


def test_suppress_does_not_hide_other_file_errors(monkeypatch, tmp_path: Path):
    def raise_permission_error(_path):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "unlink", raise_permission_error)

    with pytest.raises(PermissionError, match="permission denied"):
        delete_file_if_present(tmp_path / "protected.txt")


def test_exitstack_cleans_up_multiple_contexts_in_reverse_order():
    events = []

    result = read_multiple_documents(["one.pdf", "two.pdf"], events)

    assert result == ["Reading one.pdf", "Reading two.pdf"]
    assert events == [
        "open:one.pdf",
        "open:two.pdf",
        "read:all",
        "close:two.pdf",
        "close:one.pdf",
    ]


def test_exitstack_cleans_up_all_entered_contexts_when_exception_occurs():
    events = []

    with pytest.raises(RuntimeError, match="reading failed"):
        with ExitStack() as stack:
            stack.enter_context(managed_document("one.pdf", events))
            stack.enter_context(managed_document("two.pdf", events))
            raise RuntimeError("reading failed")

    assert events == [
        "open:one.pdf",
        "open:two.pdf",
        "close:two.pdf",
        "close:one.pdf",
    ]
