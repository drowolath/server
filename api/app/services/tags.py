import re


def normalize_tag(raw: str) -> str:
    """Normalize a tag to its canonical form.

    Strips whitespace, lowercases, and truncates to 50 characters.
    This is the single point of tag normalization — all code paths that create
    or look up tags MUST call this function first.
    """
    return raw.strip().lower()[:50]


_VALID_TAG_PATTERN = re.compile(r"^[a-z0-9._-]+$")


def validate_tag(normalized: str) -> bool:
    """Check that a normalized tag is valid.

    A valid tag is non-empty after normalization and contains only alphanumeric
    characters, hyphens, dots, and underscores (no spaces, no special characters).

    Args:
        normalized: A tag that has already been through normalize_tag().

    Returns:
        True if the tag is valid, False otherwise.
    """
    if not normalized:
        return False
    return bool(_VALID_TAG_PATTERN.match(normalized))
