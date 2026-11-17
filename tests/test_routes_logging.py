import logging
from types import SimpleNamespace

from app.routes import AskRequest, ask_question
from app.rag import NO_DOCUMENTS_ANSWER, Answer


def test_ask_logs_progress_without_logging_the_question(caplog):
    question = "Private question that must not appear in logs"
    services = SimpleNamespace(
        rag=SimpleNamespace(
            answer=lambda _question, _document_id, owner_id=None: Answer(
                NO_DOCUMENTS_ANSWER, []
            )
        )
    )

    with caplog.at_level(logging.INFO, logger="app.routes"):
        ask_question(
            AskRequest(question=question), services, SimpleNamespace(user_id="test-user")
        )

    assert [record.message for record in caplog.records] == [
        "Ask request received.",
    ]
    assert question not in caplog.text
