"""Shared, dependency-free tokenization for the local demo providers."""

import re


_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
    "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "he", "her", "hers", "him", "his", "how", "i", "if",
    "in", "into", "is", "it", "its", "may", "me", "might", "my", "of",
    "on", "or", "our", "ours", "she", "should", "that", "the", "their",
    "theirs", "them", "there", "these", "they", "this", "those", "to",
    "was", "we", "were", "what", "when", "where", "which", "who", "why",
    "will", "with", "would", "you", "your", "yours",
}


def local_tokens(text: str) -> list[str]:
    """Return lowercase content words; this deliberately does not do NLP stemming."""
    return [
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOP_WORDS
    ]
