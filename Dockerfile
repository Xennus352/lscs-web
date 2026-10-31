FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install slowapi and uvicorn explicitly
RUN pip install --no-cache-dir slowapi uvicorn pyjwt openpyxl

# Copy application code
COPY app ./app
COPY assets ./assets
COPY templates ./templates
COPY .env .env
COPY run.sh ./run.sh

# Make run.sh executable
RUN chmod +x ./run.sh

# Expose the port the app runs on
EXPOSE 5000

# Start the application
CMD ["./run.sh"]