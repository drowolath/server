import structlog
from openai import AsyncOpenAI

from app.config import settings

log = structlog.get_logger(__name__)

OPENAI_MODEL = "text-embedding-3-small"
OPENAI_DIMENSIONS = 1536


class EmbeddingSkippedError(Exception):
    """Raised when embedding is skipped (no API key configured)."""
    pass


class EmbeddingService:
    """Generates text embeddings via OpenAI text-embedding-3-small.

    When OPENAI_API_KEY is not set, all embed() calls raise EmbeddingSkippedError
    rather than crashing — traces remain with embedding=NULL until a key is configured.
    """

    def __init__(self) -> None:
        if not settings.openai_api_key:
            self._skip = True
            log.warning(
                "openai_api_key_missing",
                message=(
                    "OPENAI_API_KEY not set — embedding worker will skip trace embedding. "
                    "Traces will not appear in semantic search until API key is configured."
                ),
            )
        else:
            self._skip = False
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """Lazy-initialize AsyncOpenAI client on first use."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def embed(self, text: str) -> tuple[list[float], str, str]:
        """Generate embedding for the given text.

        Returns:
            (embedding_vector, model_id, model_version)

        Raises:
            EmbeddingSkippedError: When no OPENAI_API_KEY is configured.
        """
        if self._skip:
            raise EmbeddingSkippedError(
                "Embedding skipped: OPENAI_API_KEY not configured."
            )

        client = self._get_client()
        response = await client.embeddings.create(
            input=text,
            model=OPENAI_MODEL,
            dimensions=OPENAI_DIMENSIONS,
        )
        vector = response.data[0].embedding
        model_version = response.model
        return (vector, OPENAI_MODEL, model_version)
