import re


def keyword_pattern(term: str) -> re.Pattern[str]:
    """Case-insensitive whole-word match for `term`, tolerating a plural suffix."""
    return re.compile(rf"\b{re.escape(term)}(?:s|es)?\b", re.IGNORECASE)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
