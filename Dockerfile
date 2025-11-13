# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for PDF processing
RUN apt-get update && apt-get install -y \
    bash \
    # Required for PyMuPDF
    libmupdf-dev \
    mupdf-tools \
    # Required for ReportLab and image processing
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    build-essential \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Add Ghostscript for font embedding
RUN apt-get update && apt-get install -y ghostscript && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for uploads and outputs
RUN mkdir -p /app/uploads /app/outputs /app/temp

# Expose port (use 8080 for DO App Platform compatibility)
EXPOSE 8080

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

# Use Gunicorn entrypoint by default (production/staging)
# Dev compose overrides this with --reload.
COPY scripts/start.sh /app/scripts/start.sh
COPY gunicorn_conf.py /app/gunicorn_conf.py
RUN chmod +x /app/scripts/start.sh

CMD ["/app/scripts/start.sh"]
