FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini .
COPY fixtures/ fixtures/
COPY scripts/ scripts/

RUN pip install --no-cache-dir .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
