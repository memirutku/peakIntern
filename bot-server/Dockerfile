FROM python:3.11-slim

# Python ortam değişkenleri
# PYTHONDONTWRITEBYTECODE=1 : .pyc dosyaları oluşturmaz (image boyutunu küçültür)
# PYTHONUNBUFFERED=1 : stdout/stderr buffer'ı kapatır (loglar anında görünür)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home appuser

# curl for health/debug (e.g. docker exec bot-server curl -s http://host.docker.internal:11434/api/tags)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5003

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5003/health')" || exit 1

# Run with gunicorn - longer timeout for LLM operations
CMD ["gunicorn", "--bind", "0.0.0.0:5003", "--workers", "2", "--timeout", "600", "app:app"]
