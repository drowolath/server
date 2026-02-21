FROM python:3.12-slim AS base

RUN pip install uv

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini .
COPY fixtures/ fixtures/
COPY scripts/ scripts/

RUN uv venv /app/.venv && /app/.venv/bin/pip install .

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
