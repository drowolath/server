## Stage 1: Build static site
FROM python:3.12-slim AS builder

WORKDIR /build

COPY frontend/pyproject.toml .
RUN pip install --no-cache-dir .

COPY frontend/build.py .
COPY frontend/templates/ templates/
COPY frontend/static/ static/
COPY api/fixtures/seed_traces.json seed_traces.json

RUN python build.py

## Stage 2: Serve with nginx
FROM nginx:alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=builder /build/_site /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
