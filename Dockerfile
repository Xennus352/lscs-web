FROM python:3.12-slim

WORKDIR /app

# System dependencies: build tools for wheels, MariaDB for the embedded database
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    mariadb-server \
    mariadb-client \
    && rm -rf /var/lib/apt/lists/*

# Initialise the embedded database at build time (runtime starts faster)
RUN rm -rf /var/lib/mysql \
    && mkdir -p /var/lib/mysql /run/mysqld \
    && mariadb-install-db --user=mysql --datadir=/var/lib/mysql \
         --auth-root-authentication-method=normal >/dev/null \
    && chown -R mysql:mysql /var/lib/mysql /run/mysqld

# Copy requirements first for caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir slowapi uvicorn pyjwt openpyxl

# Copy application code
COPY app ./app
COPY assets ./assets
COPY templates ./templates
COPY deploy/seed.sql ./deploy/seed.sql
COPY run.sh ./run.sh
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./run.sh ./docker-entrypoint.sh

EXPOSE 5000

# Embedded-database mode unless DATABASE_URL is provided at run time
CMD ["./docker-entrypoint.sh"]
