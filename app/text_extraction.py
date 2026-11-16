"""Validate and extract text from supported TXT and PDF uploads."""

from io import BytesIO
from pathlib import PurePath

from app.errors import InvalidDocumentError
from app.models import ExtractedPage


SUPPORTED_EXTENSIONS = {".txt", ".pdf"}


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


def extract_text(filename: str, content: bytes) -> list[ExtractedPage]:
    """Extract non-empty text pages after checking extension and file signature."""
    validate_filename(filename)
    if not content:
        raise InvalidDocumentError("The uploaded document is empty.")

    if filename.lower().endswith(".txt"):
        try:
            text = content.decode("utf-8-sig").strip()
        except UnicodeDecodeError as error:
            raise InvalidDocumentError("TXT files must use UTF-8 encoding.") from error
        if not text:
            raise InvalidDocumentError("The document contains no extractable text.")
        return [ExtractedPage(text=text)]

    if not content.startswith(b"%PDF-"):
        raise InvalidDocumentError("The uploaded content is not a valid PDF file.")

    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise InvalidDocumentError("Encrypted PDF files are not supported.")
        pages = [
            ExtractedPage(text=text.strip(), page_number=number)
            for number, page in enumerate(reader.pages, start=1)
            if (text := page.extract_text() or "").strip()
        ]
    except InvalidDocumentError:
        raise
    except Exception as error:
        raise InvalidDocumentError("The PDF could not be read.") from error

    if not pages:
        raise InvalidDocumentError("The document contains no extractable text.")
    return pages
