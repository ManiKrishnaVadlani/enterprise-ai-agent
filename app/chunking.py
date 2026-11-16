"""Character-window text chunking with a configurable overlap."""


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into non-empty windows, preferring word boundaries."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            boundary = cleaned.rfind(" ", start, end)
            if boundary > start:
                end = boundary

        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(cleaned):
            break
        next_start = max(start + 1, end - overlap)
        if (
            next_start < len(cleaned)
            and cleaned[next_start] != " "
            and cleaned[next_start - 1] != " "
        ):
            word_start = cleaned.rfind(" ", start, next_start)
            if word_start >= start:
                next_start = word_start + 1
        start = next_start
        while start < len(cleaned) and cleaned[start] == " ":
            start += 1
    return chunks
