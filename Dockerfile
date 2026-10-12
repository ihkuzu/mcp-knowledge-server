FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MCPKB_DOCS_DIR=/app/data/docs MCPKB_DB_PATH=/app/data/shop.db
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .
COPY data ./data
RUN mcpkb init-db

RUN useradd --create-home app
USER app
EXPOSE 8000
CMD ["mcpkb", "serve", "--http", "--host", "0.0.0.0", "--port", "8000"]
