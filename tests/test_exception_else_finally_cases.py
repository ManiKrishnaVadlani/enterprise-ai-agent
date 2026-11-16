from test_exception_else_finally import parse_integer


def test_else_runs_when_try_succeeds():
    events = []

    result = parse_integer("42", events)

    assert result == 42
    assert events == ["try", "else", "finally"]


def test_except_runs_and_else_is_skipped_when_try_fails():
    events = []

    result = parse_integer("not a number", events)

    assert result is None
    assert events == ["try", "except", "finally"]


def test_finally_runs_after_both_success_and_failure():
    successful_events = []
    failed_events = []

    parse_integer("7", successful_events)
    parse_integer("not a number", failed_events)

    assert successful_events[-1] == "finally"
    assert failed_events[-1] == "finally"
