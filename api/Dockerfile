FROM python:3.12-slim AS base

RUN pip install uv

WORKDIR /app

COPY pyproject.toml .

RUN uv sync --frozen --no-dev || uv sync --no-dev

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
