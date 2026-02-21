"""PII/secrets scanning gate for CommonTrace submissions.

This module provides synchronous scanning functions that act as the primary
safety gate (SAFE-02) preventing credentials, API keys, and PII from entering
the trace database.

Design note on false positives (see research open question 3):
- We use all detectors on all fields (title, context_text, solution_text) to
  keep the implementation simple and secure.
- False positives (e.g. the word "password" appearing in a debugging description)
  ARE possible, but are preferable to missed secrets leaking into the database.
- We use enable_eager_search=False to only match secrets in quoted strings or
  specific patterns (AWS keys, JWTs, etc.), which significantly reduces false
  positives compared to bare-word scanning. Normal descriptive text will not
  trigger the scanner.
- KeywordDetector IS enabled on solution_text. If someone writes
  password = "hunter2" in their solution, that is an actual credential leak
  and should be blocked.
"""

from detect_secrets.core.scan import _scan_line
from detect_secrets.settings import default_settings, get_plugins
from detect_secrets.util.code_snippet import CodeSnippet


class SecretDetectedError(Exception):
    """Raised when a scan detects one or more potential secrets in submitted text.

    Attributes:
        secret_types: The set of secret type names that were detected.
                      The actual secret values are intentionally NOT included
                      to avoid echoing credentials back to the caller.
    """

    def __init__(self, secret_types: set[str]) -> None:
        self.secret_types = secret_types
        super().__init__(
            f"Potential secret(s) detected in submitted content: {secret_types}. "
            "Remove credentials before submitting."
        )


def scan_content(text: str) -> None:
    """Scan a block of text for potential secrets or credentials.

    Uses detect-secrets with enable_eager_search=False so that only quoted
    strings and specific structured patterns (AWS keys, JWTs, etc.) are
    matched — normal descriptive prose is not flagged.

    Args:
        text: The text to scan.

    Raises:
        SecretDetectedError: If any potential secret is found. The exception
            carries the set of detected secret type names but NOT the values.
    """
    found_types: set[str] = set()

    with default_settings():
        for line in text.splitlines():
            if not line.strip():
                continue
            context = CodeSnippet(snippet=[line], start_line=1, target_index=0)
            for plugin in get_plugins():
                for secret in _scan_line(
                    plugin=plugin,
                    filename="user-input",
                    line=line,
                    line_number=0,
                    context=context,
                    enable_eager_search=False,  # Requires quotes or explicit patterns
                ):
                    found_types.add(secret.type)

    if found_types:
        raise SecretDetectedError(secret_types=found_types)


def scan_trace_submission(title: str, context_text: str, solution_text: str) -> None:
    """Scan all three fields of a trace submission for secrets.

    All fields are scanned with the same detector set including KeywordDetector.
    This is intentionally conservative — a debugging description that mentions
    an actual credential value will be blocked, which is the correct behavior.

    Normal text (e.g. "the token endpoint requires authentication") will NOT
    be flagged because we require quoted strings or specific known patterns.

    Args:
        title: The trace title.
        context_text: The problem/context description.
        solution_text: The solution description.

    Raises:
        SecretDetectedError: If any field contains a potential secret.
    """
    scan_content(title)
    scan_content(context_text)
    scan_content(solution_text)


def scan_amendment_submission(improved_solution: str, explanation: str) -> None:
    """Scan both fields of an amendment submission for secrets.

    Args:
        improved_solution: The improved solution text.
        explanation: The explanation of why the amendment is better.

    Raises:
        SecretDetectedError: If either field contains a potential secret.
    """
    scan_content(improved_solution)
    scan_content(explanation)
