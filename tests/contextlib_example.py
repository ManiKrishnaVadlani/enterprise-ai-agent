"""Practical examples of helpers from Python's contextlib module."""

from contextlib import ExitStack, contextmanager, suppress
from pathlib import Path
from typing import Generator


@contextmanager
def managed_document(name: str, events: list[str]) -> Generator[str, None, None]:
    """Log setup and cleanup around the code inside a with-block."""
    events.append(f"open:{name}")
    try:
        yield name
    finally:
        events.append(f"close:{name}")


def read_document(name: str, events: list[str]) -> str:
    """Read a pretend document while its managed context is active."""
    with managed_document(name, events) as document_name:
        events.append(f"read:{document_name}")
        return f"Reading {document_name}"


def delete_file_if_present(path: str | Path) -> bool:
    """Delete a file, quietly doing nothing if it is already missing."""
    deleted = False
    with suppress(FileNotFoundError):
        Path(path).unlink()
        deleted = True
    return deleted


def read_multiple_documents(
    names: list[str], events: list[str]
) -> list[str]:
    """Manage several document contexts together with ExitStack."""
    with ExitStack() as stack:
        documents = [
            stack.enter_context(managed_document(name, events)) for name in names
        ]
        events.append("read:all")
        return [f"Reading {name}" for name in documents]


if __name__ == "__main__":
    activity: list[str] = []
    print(read_document("handbook.pdf", activity))
    print(activity)
