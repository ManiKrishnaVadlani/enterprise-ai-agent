import sys
from io import BytesIO
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.errors import InvalidDocumentError
from app.text_extraction import clean_text, extract_text, validate_filename


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


def test_txt_extraction_handles_bom_newlines_unicode_and_paragraphs():
    pages = extract_text(
        "unicode.txt",
        "\ufeffCafe\u0301\r\n\r\nKeep 東京 safe.\r".encode("utf-8"),
    )

    assert pages[0].text == "Café\n\nKeep 東京 safe."


def test_text_cleaning_collapses_noise_but_preserves_meaningful_layout():
    cleaned = clean_text("  Heading\t One  \r\n\r\n\r\nBody\x00 text!  \r")

    assert cleaned == "Heading One\n\nBody text!"


def test_txt_rejects_whitespace_only_content_after_cleaning():
    with pytest.raises(InvalidDocumentError, match="no extractable text"):
        extract_text("blank.txt", b" \t\r\n \r\n")


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


def test_pdf_extraction_normalizes_text_and_ignores_empty_pages(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class FakeReader:
        is_encrypted = False
        pages = [
            FakePage("  Policy\r\n\r\n Keep  café safe. "),
            FakePage(" \t\r\n "),
            FakePage("Page three — résumé."),
        ]

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=FakeReader))
    pages = extract_text("report.pdf", b"%PDF-1.7")

    assert [(page.text, page.page_number) for page in pages] == [
        ("Policy\n\nKeep café safe.", 1),
        ("Page three — résumé.", 3),
    ]


def test_corrupt_pdf_errors_are_safe_and_image_only_pdf_is_rejected(monkeypatch):
    class BrokenReader:
        is_encrypted = False

        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("private parser details")

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=BrokenReader))
    with pytest.raises(InvalidDocumentError, match="PDF could not be read") as error:
        extract_text("broken.pdf", b"%PDF-1.7")
    assert "private parser details" not in str(error.value)

    class ImageOnlyReader:
        is_encrypted = False
        pages = [
            SimpleNamespace(extract_text=lambda: ""),
            SimpleNamespace(extract_text=lambda: None),
        ]

        def __init__(self, *_args, **_kwargs):
            pass

    monkeypatch.setitem(
        sys.modules, "pypdf", SimpleNamespace(PdfReader=ImageOnlyReader)
    )
    with pytest.raises(InvalidDocumentError, match="no extractable text"):
        extract_text("scan.pdf", b"%PDF-1.7")
