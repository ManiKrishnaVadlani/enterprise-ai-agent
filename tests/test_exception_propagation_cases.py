import pytest

from test_exception_propagation import answer_from_document, load_with_logging


def _traceback_function_names(exception):
    """Return function names recorded in the exception's original traceback."""
    names = []
    traceback = exception.__traceback__
    while traceback is not None:
        names.append(traceback.tb_frame.f_code.co_name)
        traceback = traceback.tb_next
    return names


def test_missing_document_error_propagates_through_function_calls():
    with pytest.raises(FileNotFoundError, match="Document not found: handbook.pdf") as error:
        answer_from_document("handbook.pdf")

    traceback_functions = _traceback_function_names(error.value)

    assert "answer_from_document" in traceback_functions
    assert "prepare_document" in traceback_functions
    assert "open_document" in traceback_functions


def test_bare_raise_preserves_original_exception_and_traceback():
    with pytest.raises(FileNotFoundError, match="Document not found: handbook.pdf") as error:
        load_with_logging("handbook.pdf")

    traceback_functions = _traceback_function_names(error.value)

    assert "load_with_logging" in traceback_functions
    assert "open_document" in traceback_functions
