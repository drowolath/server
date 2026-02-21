import re


def normalize_tag(raw: str) -> str:
    """Normalize a tag to its canonical form.

    Strips whitespace, lowercases, and truncates to 50 characters.
    This is the single point of tag normalization — all code paths that create
    or look up tags MUST call this function first.
    """
    return raw.strip().lower()[:50]


def normalize_tags(raw_tags: list[str]) -> list[str]:
    """Apply normalize_tag to each tag, then deduplicate preserving order.

    Returns unique normalized tags in the order first encountered.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_tags:
        normalized = normalize_tag(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


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
