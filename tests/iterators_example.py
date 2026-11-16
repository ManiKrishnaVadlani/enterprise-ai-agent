"""Examples of iterables, iterators, and Python's iterator protocol."""


class DocumentCollection:
    """An iterable collection that can create a fresh iterator each time."""

    def __init__(self, names: list[str]):
        self._names = tuple(names)

    def __iter__(self):
        """Return an iterator; iter(collection) calls this method."""
        return iter(self._names)


class CountdownIterator:
    """A custom one-pass iterator that counts down to zero."""

    def __init__(self, start: int):
        self._current = start

    def __iter__(self):
        """An iterator is also iterable, so return this same object."""
        return self

    def __next__(self):
        """Return the next number or signal that the iterator is exhausted."""
        if self._current <= 0:
            raise StopIteration

        number = self._current
        self._current -= 1
        return number


def compare_document_sources(names: list[str]) -> list[str]:
    """Print a short practical comparison of a list, iterator, and generator."""
    documents = list(names)
    print(f"List keeps all values: {documents}")

    document_iterator = iter(documents)
    print(f"Iterator next value: {next(document_iterator)}")
    print(f"List is still reusable: {documents}")

    document_generator = (name for name in documents)
    print(f"Generator next value: {next(document_generator)}")
    remaining = list(document_generator)
    print(f"Generator remaining values: {remaining}")
    return remaining


if __name__ == "__main__":
    collection = DocumentCollection(["handbook.pdf", "policy.pdf"])
    collection_iterator = iter(collection)
    print(next(collection_iterator))
    print(list(CountdownIterator(3)))
    compare_document_sources(["handbook.pdf", "policy.pdf"])
