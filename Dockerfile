FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONPATH="/app/src"
ENV PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    tesseract-ocr \
    tesseract-ocr-vie \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick security policy
RUN sed -i '/<policy domain="path" rights="none" pattern="@\*"/d' \
    /etc/ImageMagick-6/policy.xml 2>/dev/null || true

# Python dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[api]" 2>/dev/null || \
    pip install --no-cache-dir -e . 2>/dev/null || true

COPY . .
RUN pip install --no-cache-dir -e ".[api]" 2>/dev/null || \
    pip install --no-cache-dir -e . || true

EXPOSE 8080 8501

# Default: run API server
CMD ["uvicorn", "bookai.api:app", "--host", "0.0.0.0", "--port", "8080"]
