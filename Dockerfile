FROM python:3.11-slim

# Install system dependencies including FFmpeg for video/audio muxing and curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create non-root user for Hugging Face Spaces security standards
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Hugging Face Spaces standard port is 7860
EXPOSE 7860

# Run Gunicorn with 4 workers and 120s timeout
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:7860", "--timeout", "120", "app:app"]
