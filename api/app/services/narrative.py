"""Narrative synthesis service for pattern trace generation.

Synthesizes convergence clusters of 5+ episodic traces into a single
"pattern trace" — a distilled, generalized solution that captures the
common thread across multiple independent solutions to the same problem.

Uses Anthropic Claude (claude-haiku-4-5) for synthesis, matching the
architecture where Claude is the primary LLM powering agents.
"""

import structlog
from app.config import settings

log = structlog.get_logger(__name__)

SYNTHESIS_MODEL = "claude-haiku-4-5-20251001"
MAX_SOURCE_TRACES = 10
MAX_OUTPUT_TOKENS = 1500


class NarrativeSkippedError(Exception):
    """Raised when narrative synthesis is skipped (no API key)."""
    pass


class NarrativeService:
    def __init__(self) -> None:
        self._skip = not settings.anthropic_api_key
        self._client = None
        if self._skip:
            log.warning("narrative_service_no_api_key")

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
            )
        return self._client

    async def synthesize_cluster(
        self,
        traces: list[dict],
        convergence_level: int,
    ) -> dict:
        """Synthesize a cluster of traces into a pattern trace.

        Args:
            traces: List of dicts with keys: title, context_text,
                    solution_text, tags, trust_score
            convergence_level: 0-4 from convergence detection

        Returns:
            dict with keys: title, context_text, solution_text, tags

        Raises:
            NarrativeSkippedError: When no API key configured.
        """
        if self._skip:
            raise NarrativeSkippedError("ANTHROPIC_API_KEY not configured")

        client = self._get_client()

        # Build the source material
        source_descriptions = []
        all_tags: set[str] = set()
        for i, t in enumerate(traces[:MAX_SOURCE_TRACES], 1):
            source_descriptions.append(
                f"### Source {i}: {t['title']}\n"
                f"**Context:** {t['context_text'][:300]}\n"
                f"**Solution:** {t['solution_text'][:500]}\n"
                f"**Tags:** {', '.join(t.get('tags', []))}"
            )
            for tag in t.get("tags", []):
                all_tags.add(tag)

        level_descriptions = {
            0: "universal (cross-language)",
            1: "ecosystem (same language family)",
            2: "stack-agnostic (same language, different frameworks)",
            3: "environment-agnostic (same stack, different OS)",
            4: "contextual (single environment)",
        }
        level_desc = level_descriptions.get(convergence_level, "contextual")

        system_prompt = (
            "You are a technical knowledge synthesizer. Given multiple "
            "independent solutions to the same problem, distill them into "
            "a single generalized pattern trace. Focus on the common "
            "thread — what is the underlying problem, and what is the "
            "consensus solution approach? Do NOT copy verbatim from "
            "sources. Write as if explaining to a developer who has never "
            "seen any of the individual traces."
        )

        user_prompt = (
            f"Synthesize these {len(traces)} traces into one pattern trace.\n"
            f"Convergence level: {level_desc}\n\n"
            + "\n\n".join(source_descriptions)
            + "\n\nOutput format (use exactly these headers):\n"
            "TITLE: <concise title for the pattern>\n"
            "CONTEXT: <1-3 sentences describing the common problem>\n"
            "SOLUTION: <generalized solution with code if applicable>\n"
            "TAGS: <comma-separated tags>"
        )

        response = await client.messages.create(
            model=SYNTHESIS_MODEL,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=MAX_OUTPUT_TOKENS,
        )

        text = response.content[0].text
        return _parse_synthesis_output(text, list(all_tags))


def _parse_synthesis_output(text: str, fallback_tags: list[str]) -> dict:
    """Parse the LLM output into structured fields."""
    result = {
        "title": "",
        "context_text": "",
        "solution_text": "",
        "tags": fallback_tags,
    }

    current_field = None
    current_content: list[str] = []

    for line in text.strip().split("\n"):
        upper = line.strip().upper()
        if upper.startswith("TITLE:"):
            if current_field:
                result[current_field] = "\n".join(current_content).strip()
            current_field = "title"
            current_content = [line.split(":", 1)[1].strip()]
        elif upper.startswith("CONTEXT:"):
            if current_field:
                result[current_field] = "\n".join(current_content).strip()
            current_field = "context_text"
            current_content = [line.split(":", 1)[1].strip()]
        elif upper.startswith("SOLUTION:"):
            if current_field:
                result[current_field] = "\n".join(current_content).strip()
            current_field = "solution_text"
            current_content = [line.split(":", 1)[1].strip()]
        elif upper.startswith("TAGS:"):
            if current_field:
                result[current_field] = "\n".join(current_content).strip()
            tag_text = line.split(":", 1)[1].strip()
            result["tags"] = [
                t.strip().lower() for t in tag_text.split(",") if t.strip()
            ]
            current_field = None
            current_content = []
        else:
            current_content.append(line)

    if current_field:
        result[current_field] = "\n".join(current_content).strip()

    return result
