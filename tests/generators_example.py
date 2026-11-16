"""Beginner examples showing how Python generators produce values lazily."""


def normal_document_names(count: int) -> list[str]:
    """Build and return every document name immediately as a list."""
    return [f"document-{number}" for number in range(count)]


def document_name_generator(count: int, events: list[str]):
    """Produce one document name at a time and record when it is produced."""
    for number in range(count):
        name = f"document-{number}"
        events.append(f"generated:{name}")
        yield name


def number_steps():
    """Yield a few values, keeping this function's position between calls."""
    yield 1
    yield 2
    yield 3


def square_numbers(limit: int):
    """Return a generator expression instead of building a list of squares."""
    return (number * number for number in range(limit))


def cleanup_generator(events: list[str]):
    """Show that generator cleanup runs when it is closed or receives an error."""
    try:
        yield "first record"
        yield "second record"
    finally:
        events.append("generator cleaned up")


if __name__ == "__main__":
    activity: list[str] = []
    names = document_name_generator(2, activity)
    print(next(names))
    print(list(names))
    print(activity)
    print(list(square_numbers(4)))
