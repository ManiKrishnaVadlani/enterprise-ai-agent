import pytest

from test_exception_hierarchy import catch_expected_error, describe_exception_hierarchy


@pytest.mark.parametrize(
    ("child", "parent"),
    [
        (Exception, BaseException),
        (ValueError, Exception),
        (TypeError, Exception),
        (KeyError, LookupError),
        (IndexError, LookupError),
        (FileNotFoundError, OSError),
        (OSError, Exception),
    ],
)
def test_representative_builtin_exceptions_have_expected_parents(child, parent):
    assert issubclass(child, parent)


def test_example_map_shows_common_hierarchy_branches():
    hierarchy = describe_exception_hierarchy()

    assert "Exception" in hierarchy["BaseException"]
    assert {"ValueError", "TypeError", "LookupError", "OSError"} <= set(
        hierarchy["Exception"]
    )
    assert set(hierarchy["LookupError"]) == {"KeyError", "IndexError"}
    assert "FileNotFoundError" in hierarchy["OSError"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (KeyError("name"), "Lookup problem: KeyError"),
        (IndexError("position"), "Lookup problem: IndexError"),
        (FileNotFoundError("notes.txt"), "File problem: FileNotFoundError"),
        (ValueError("bad value"), "Application problem: ValueError"),
    ],
)
def test_parent_handlers_catch_child_errors(error, expected):
    assert catch_expected_error(error) == expected
