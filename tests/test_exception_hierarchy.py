"""Learning example for Python's built-in exception hierarchy.

Most application errors inherit from Exception. Catching a parent class also
catches its child classes, so handlers can group related errors when useful.
"""


def describe_exception_hierarchy() -> dict[str, tuple[str, ...]]:
    """Return a small map of useful parent-to-child relationships."""
    return {
        "BaseException": ("Exception", "KeyboardInterrupt", "SystemExit"),
        "Exception": ("ValueError", "TypeError", "LookupError", "OSError"),
        "LookupError": ("KeyError", "IndexError"),
        "OSError": ("FileNotFoundError",),
    }


def catch_expected_error(error: Exception) -> str:
    """Handle ordinary application errors without swallowing process signals."""
    try:
        raise error
    except LookupError as caught_error:
        # KeyError and IndexError are both children of LookupError.
        return f"Lookup problem: {type(caught_error).__name__}"
    except OSError as caught_error:
        # FileNotFoundError is one specific kind of operating-system error.
        return f"File problem: {type(caught_error).__name__}"
    except Exception as caught_error:
        # Use this fallback only when the layer can handle ordinary errors
        # consistently; prefer specific exception types when possible.
        return f"Application problem: {type(caught_error).__name__}"
