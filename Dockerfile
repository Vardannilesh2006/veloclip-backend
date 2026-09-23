FROM python:3.11-slim

# Install system dependencies including FFmpeg for video/audio muxing, nodejs for JS challenges, and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
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

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port (Render uses 10000, Hugging Face uses 7860)
EXPOSE 7860 10000

# Run Gunicorn with dynamic PORT support
CMD ["sh", "-c", "gunicorn -w 2 -b 0.0.0.0:${PORT:-10000} --timeout 120 app:app"]
