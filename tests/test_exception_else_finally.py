"""Learning example for try, except, else, and finally."""


def parse_integer(value: str, events: list[str]) -> int | None:
    """Convert text to an integer and record the blocks that execute."""
    events.append("try")

    try:
        result = int(value)
    except ValueError:
        events.append("except")
        return None
    else:
        events.append("else")
        return result
    finally:
        events.append("finally")
