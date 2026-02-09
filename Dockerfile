# Use Python 3.13 slim image for best performance
# Python 3.13 features:
# - 5-15% faster than 3.12 (up to 30% with JIT)
# - Experimental JIT compiler (PEP 744)
# - Free-threading mode (no-GIL, PEP 703)
# - 7% smaller memory footprint
# - Better error messages and debugging
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies including ffmpeg and curl for health checks
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create directories for data persistence
RUN mkdir -p /app/data /app/logs /app/data/vavoo_playlists

# Copy Python dependencies file
COPY requirements.txt .

# Install Python dependencies with proxy support
# Using --no-cache-dir to reduce image size
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install additional proxy dependencies for better compatibility
RUN pip install --no-cache-dir \
    cryptography>=43.0.3 \
    pycryptodome>=3.21.0

# Note: Proxy support (shadowsocks, socks5, http) is included in requirements.txt

# Copy application files
COPY app-docker.py app.py
COPY stb.py .
COPY stb_scanner.py .
COPY stb_async.py .
COPY utils.py .
COPY scanner.py .
COPY scanner_async.py .
COPY scanner_scheduler.py .
COPY mac_pattern_generator.py .
COPY migrate_vpn_detection.py .
COPY templates/ templates/
COPY static/ static/

# Copy Vavoo files
COPY vavoo/ vavoo/

# Copy startup script
COPY start.sh .
RUN chmod +x start.sh

# Copy documentation files (optional)
COPY docs/ docs/

# Create non-root user for security
RUN useradd -m -u 1000 macreplayxc && \
    chown -R root:root /app

# Switch to non-root user
#USER macreplay

# Set environment variables for containerized deployment
# Note: HOST will be overridden by docker-compose.yml with your public URL
ENV HOST=0.0.0.0:8001
ENV CONFIG=/app/data/MacReplayXC.json
ENV PYTHONUNBUFFERED=1

# Python 3.13 Performance Optimizations
ENV PYTHONOPTIMIZE=2
ENV PYTHONDONTWRITEBYTECODE=1

# Expose the application ports
EXPOSE 8001
EXPOSE 4323

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/ || exit 1

# Run both applications via startup script
CMD ["./start.sh"] 