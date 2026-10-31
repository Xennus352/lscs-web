FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBUG=false

# Copy requirements first for caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app ./app
COPY assets ./assets
COPY templates ./templates
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh

# Local default; Render supplies PORT at runtime.
EXPOSE 5000

# Run only FastAPI; configure an external database through environment variables.
CMD ["./docker-entrypoint.sh"]
