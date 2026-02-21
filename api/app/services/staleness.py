"""PyPI version staleness checker for CommonTrace.

Checks whether a library referenced in a trace's metadata is behind the
current major.minor version on PyPI. Used to flag traces that may contain
outdated advice (SAFE-04).

Design notes:
- All exceptions are caught and silently swallowed to ensure graceful degradation.
  A trace is never rejected or blocked due to a staleness check failure.
- The staleness check compares only major.minor (not patch) because patch
  releases are typically backwards-compatible bugfixes and their presence
  does not invalidate the advice in a trace.
- The PyPI JSON API is used (https://pypi.org/pypi/{name}/json) with a 3-second
  timeout to avoid blocking the request path.
"""

import httpx
from packaging.version import InvalidVersion, Version


async def check_library_staleness(library_name: str, stored_version_str: str) -> bool:
    """Check whether a stored library version is behind the current PyPI major.minor.

    Args:
        library_name: The name of the Python library (e.g. "fastapi", "requests").
        stored_version_str: The version string stored with the trace (e.g. "0.95.0").

    Returns:
        True if the stored major.minor is behind the latest PyPI major.minor.
        False in all error cases (network failure, invalid version, library not found).
    """
    try:
        stored_version = Version(stored_version_str)
    except InvalidVersion:
        return False

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"https://pypi.org/pypi/{library_name}/json",
                follow_redirects=True,
            )
            if response.status_code != 200:
                return False

            data = response.json()
            latest_version_str = data.get("info", {}).get("version", "")
            if not latest_version_str:
                return False

            latest_version = Version(latest_version_str)
    except Exception:
        # Never block or fail on a staleness check — network issues, parsing errors,
        # rate limits, etc. should all result in a graceful "not stale" result.
        return False

    stored_major_minor = (stored_version.major, stored_version.minor)
    latest_major_minor = (latest_version.major, latest_version.minor)

    return stored_major_minor < latest_major_minor


async def check_trace_staleness(metadata_json: dict | None) -> bool:
    """Convenience wrapper that extracts library metadata and checks staleness.

    Intended to be called at submission time to determine whether the referenced
    library is current. A missing or malformed metadata_json simply returns False.

    Args:
        metadata_json: The trace's metadata_json field value. Expected to contain
            "library" and "library_version" keys when library metadata is present.

    Returns:
        True if the library is stale (stored version behind PyPI latest major.minor).
        False if metadata is absent, keys are missing, or any error occurs.
    """
    if not metadata_json:
        return False

    library_name = metadata_json.get("library")
    library_version = metadata_json.get("library_version")

    if not library_name or not library_version:
        return False

    return await check_library_staleness(library_name, str(library_version))
