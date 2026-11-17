import sys
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.errors import InvalidDocumentError
from app.text_extraction import extract_text, validate_filename


def test_extract_text_reads_utf8_text():
    pages = extract_text("handbook.txt", b"  Company policy\nKeep data safe.  ")

    assert [(page.text, page.page_number) for page in pages] == [
        ("Company policy\nKeep data safe.", None)
    ]


@pytest.mark.parametrize("filename", ["../secret.txt", "folder\\secret.txt", ""])
def test_validate_filename_rejects_paths_and_empty_names(filename):
    with pytest.raises(InvalidDocumentError):
        validate_filename(filename)


def test_extract_text_rejects_unsupported_empty_and_invalid_utf8_files():
    with pytest.raises(InvalidDocumentError, match="Only PDF and TXT"):
        extract_text("image.png", b"not an image")
    with pytest.raises(InvalidDocumentError, match="empty"):
        extract_text("empty.txt", b"")
    with pytest.raises(InvalidDocumentError, match="UTF-8"):
        extract_text("bad.txt", b"\xff")


def test_text_extraction_enforces_extracted_character_limit():
    with pytest.raises(InvalidDocumentError, match="extracted text exceeds"):
        extract_text("policy.txt", b"12345", max_extracted_text_chars=4)


def test_pdf_extraction_enforces_page_and_extracted_text_limits(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "text"

    class FakeReader:
        is_encrypted = False
        pages = [FakePage(), FakePage()]

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))
    with pytest.raises(InvalidDocumentError, match="page limit"):
        extract_text("policy.pdf", b"%PDF-1.7", max_pdf_pages=1)
    with pytest.raises(InvalidDocumentError, match="extracted text exceeds"):
        extract_text("policy.pdf", b"%PDF-1.7", max_extracted_text_chars=7)


def test_pdf_extraction_preserves_page_numbers(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        is_encrypted = False
        pages = [FakePage("first page"), FakePage("  "), FakePage("third page")]

        def __init__(self, _stream, strict, **parser_limits):
            assert strict is False
            assert parser_limits == {
                "root_object_recovery_limit": 1000,
                "xref_stream_maximum_entries": 200000,
            }

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))

    pages = extract_text("report.pdf", b"%PDF-1.7\nfake bytes")

    assert [(page.text, page.page_number) for page in pages] == [
        ("first page", 1),
        ("third page", 3),
    ]


def test_pdf_extraction_reads_real_pdf_text_and_page_number():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    font_reference = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_reference}
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Hello from a real PDF) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    pdf_content = BytesIO()
    writer.write(pdf_content)

    pages = extract_text("real.pdf", pdf_content.getvalue())

    assert [(page.text, page.page_number) for page in pages] == [
        ("Hello from a real PDF", 1)
    ]


def test_pdf_extraction_rejects_invalid_signature_and_encrypted_files(monkeypatch):
    with pytest.raises(InvalidDocumentError, match="not a valid PDF"):
        extract_text("report.pdf", b"plain text")

    class EncryptedReader:
        is_encrypted = True

        def __init__(self, _stream, strict, **_parser_limits):
            pass

    monkeypatch.setitem(
        sys.modules, "pypdf", SimpleNamespace(PdfReader=EncryptedReader)
    )
    with pytest.raises(InvalidDocumentError, match="Encrypted PDF"):
        extract_text("locked.pdf", b"%PDF-1.7\nfake bytes")
