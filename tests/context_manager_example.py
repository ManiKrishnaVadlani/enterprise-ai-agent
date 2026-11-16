"""A small example of a context manager that always cleans up."""


class ManagedDocument:
    """Pretend to open a document and record when it is closed."""

    def __init__(self, name: str):
        self.name = name
        self.is_open = False

    def __enter__(self):
        self.is_open = True
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.is_open = False
        # False tells Python to let any exception from the with-block continue.
        return False


def read_document(name: str) -> str:
    """Use a document only while its context is open."""
    with ManagedDocument(name) as document:
        return f"Reading {document.name}"


if __name__ == "__main__":
    print(read_document("handbook.pdf"))
