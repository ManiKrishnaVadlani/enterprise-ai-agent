"""Deterministic structure-aware character chunking with bounded overlap."""

import re


_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])(?:[\"')\]]?)(?=\s)")
_PARAGRAPH_BOUNDARY = re.compile(r"\n\n+")
_LINE_BOUNDARY = re.compile(r"\n")
_WHITESPACE_BOUNDARY = re.compile(r"\s+")


def _looks_like_heading(line: str) -> bool:
    """Recognize short heading-like lines so a split can keep their body nearby."""
    stripped = line.strip()
    if not stripped or len(stripped) > 100 or len(stripped.split()) > 12:
        return False
    if stripped.startswith(("- ", "* ", "• ")) or re.match(r"\d+[.)]\s", stripped):
        return False
    if stripped.endswith((".", "!", "?", ";")):
        return False
    return stripped[0].isupper() or stripped.endswith(":")


def _preferred_boundary(text: str, start: int, limit: int) -> int:
    """Choose a late structural boundary, falling back to whitespace or a hard cut."""
    window = text[start:limit]
    minimum = max(1, len(window) // 2)
    priorities = (
        _PARAGRAPH_BOUNDARY,
        _SENTENCE_BOUNDARY,
        _LINE_BOUNDARY,
        _WHITESPACE_BOUNDARY,
    )
    for pattern in priorities:
        matches = list(pattern.finditer(window))
        eligible = []
        for match in matches:
            if match.start() < minimum:
                continue
            if pattern is not _SENTENCE_BOUNDARY:
                previous_line = window[: match.start()].rstrip().split("\n")[-1]
                if _looks_like_heading(previous_line):
                    continue
            eligible.append(match)
        if eligible:
            match = eligible[-1]
            if pattern is _SENTENCE_BOUNDARY:
                return start + match.start() + 1
            return start + match.start()
    return limit


def _overlap_start(text: str, end: int, start: int, overlap: int) -> int:
    """Include the preceding whole word when it slightly exceeds the overlap."""
    desired = max(start + 1, end - overlap)
    if desired >= len(text):
        return desired
    if desired > 0 and not text[desired - 1].isspace() and not text[desired].isspace():
        word_start = text.rfind(" ", start, desired)
        newline_start = text.rfind("\n", start, desired)
        boundary = max(word_start, newline_start)
        if boundary >= start:
            desired = boundary + 1
    return desired


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text at paragraphs, sentences, lines, then words when possible.

    A single unbroken token is split at a character boundary as a final fallback.
    Every returned chunk is non-empty and no longer than ``chunk_size``.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in normalized.split("\n")]
    cleaned_lines: list[str] = []
    blank_seen = False
    for line in lines:
        if line:
            cleaned_lines.append(line)
            blank_seen = False
        elif cleaned_lines and not blank_seen:
            cleaned_lines.append("")
            blank_seen = True
    cleaned = "\n".join(cleaned_lines).strip()
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        limit = min(start + chunk_size, len(cleaned))
        end = limit if limit == len(cleaned) else _preferred_boundary(cleaned, start, limit)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break

        next_start = _overlap_start(cleaned, end, start, overlap)
        while next_start < len(cleaned) and cleaned[next_start].isspace():
            next_start += 1
        if next_start <= start:
            next_start = end
        start = next_start
    return chunks
