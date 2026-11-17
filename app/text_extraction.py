"""Validate and extract text from supported TXT and PDF uploads."""

from io import BytesIO
from pathlib import PurePath

from app.errors import InvalidDocumentError
from app.models import ExtractedPage


SUPPORTED_EXTENSIONS = {".txt", ".pdf"}
DEFAULT_MAX_PDF_PAGES = 200
DEFAULT_MAX_EXTRACTED_TEXT_CHARS = 2_000_000
PDF_ROOT_OBJECT_RECOVERY_LIMIT = 1_000
PDF_XREF_STREAM_MAXIMUM_ENTRIES = 200_000


def validate_filename(filename: str) -> str:
    """Accept only a plain supported filename, never a path supplied by a client."""
    if not filename or "\x00" in filename or "/" in filename or "\\" in filename:
        raise InvalidDocumentError("Provide a filename without directory paths.")
    if len(filename) > 255 or filename in {".", ".."}:
        raise InvalidDocumentError("The filename is invalid or too long.")

    suffix = PurePath(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise InvalidDocumentError("Only PDF and TXT files are supported.")
    return filename


def extract_text(
    filename: str,
    content: bytes,
    max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES,
    max_extracted_text_chars: int = DEFAULT_MAX_EXTRACTED_TEXT_CHARS,
) -> list[ExtractedPage]:
    """Extract non-empty text pages after checking extension and file signature."""
    validate_filename(filename)
    if max_pdf_pages < 1 or max_extracted_text_chars < 1:
        raise ValueError("PDF page and extracted text limits must be positive.")
    if not content:
        raise InvalidDocumentError("The uploaded document is empty.")

    if filename.lower().endswith(".txt"):
        try:
            text = content.decode("utf-8-sig").strip()
        except UnicodeDecodeError as error:
            raise InvalidDocumentError("TXT files must use UTF-8 encoding.") from error
        if len(text) > max_extracted_text_chars:
            raise InvalidDocumentError("The extracted text exceeds the configured limit.")
        if not text:
            raise InvalidDocumentError("The document contains no extractable text.")
        return [ExtractedPage(text=text)]

    if not content.startswith(b"%PDF-"):
        raise InvalidDocumentError("The uploaded content is not a valid PDF file.")

    try:
        from pypdf import PdfReader

        reader = PdfReader(
            BytesIO(content),
            strict=False,
            root_object_recovery_limit=PDF_ROOT_OBJECT_RECOVERY_LIMIT,
            xref_stream_maximum_entries=PDF_XREF_STREAM_MAXIMUM_ENTRIES,
        )
        if reader.is_encrypted:
            raise InvalidDocumentError("Encrypted PDF files are not supported.")
        if len(reader.pages) > max_pdf_pages:
            raise InvalidDocumentError("The PDF exceeds the configured page limit.")
        pages = []
        total_characters = 0
        for number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            total_characters += len(text)
            if total_characters > max_extracted_text_chars:
                raise InvalidDocumentError(
                    "The extracted text exceeds the configured limit."
                )
            if text.strip():
                pages.append(ExtractedPage(text=text.strip(), page_number=number))
    except InvalidDocumentError:
        raise
    except Exception as error:
        raise InvalidDocumentError("The PDF could not be read.") from error

    if not pages:
        raise InvalidDocumentError("The document contains no extractable text.")
    return pages
