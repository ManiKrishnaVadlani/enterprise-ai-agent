from datetime import datetime, timezone

from app.models import DocumentSummary
from main import app
from app.routes import DocumentResponse


def test_openapi_documents_required_routes_and_binary_document_upload():
    schema = app.openapi()
    paths = schema["paths"]

    assert "get" in paths["/"]
    assert "get" in paths["/health"]
    assert "get" in paths["/ready"]
    assert "post" in paths["/documents/upload"]
    upload_content = paths["/documents/upload"]["post"]["requestBody"]["content"]
    assert "application/octet-stream" in upload_content
    assert "get" in paths["/documents"]
    assert "delete" in paths["/documents/{document_id}"]
    assert "post" in paths["/ask"]


def test_document_dataclasses_serialize_through_api_response_model():
    document = DocumentSummary(
        "doc-id", "policy.txt", datetime(2026, 1, 1, tzinfo=timezone.utc), 2
    )

    response = DocumentResponse.model_validate(document)

    assert response.document_id == "doc-id"
    assert response.filename == "policy.txt"
    assert response.chunk_count == 2
