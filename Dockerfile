FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Build wheels required by the pinned runtime dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install the locked Paper-only runtime.
COPY requirements.lock.txt .
RUN python -m pip install --upgrade pip && python -m pip install --no-cache-dir -r requirements.lock.txt

# Copy application code
COPY . .

# Ensure data directory exists
RUN mkdir -p data

# Streamable HTTP entry point. Platform deployment remains outside this stage.
CMD ["python", "app/main.py"]
