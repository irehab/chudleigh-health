FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Force gRPC to use the native system DNS resolver
    GRPC_DNS_RESOLVER=native

# Install system certificates and network protocols for secure cloud routing, and the text-recognition (OCR) program
# the PDF reader uses for reports that are pictures
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    netbase \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy only the application code (not .env files, keys, PDFs, tests, etc.). Owned by root, so read-only for appuser.
COPY app.py helpers.py ./
COPY pdf_reader ./pdf_reader
COPY norms ./norms

USER appuser

EXPOSE 8080

# Theme: the Health Autonomy at Chudleigh Health Hub colours (teal buttons and links, soft off-white backgrounds, charcoal text)
CMD ["streamlit", "run", "app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.maxUploadSize=20", \
     "--server.enableXsrfProtection=true", \
     "--browser.gatherUsageStats=false", \
     "--client.showErrorDetails=none", \
     "--client.toolbarMode=viewer", \
     "--theme.base=light", \
     "--theme.primaryColor=#3D7F88", \
     "--theme.backgroundColor=#FBFBFA", \
     "--theme.secondaryBackgroundColor=#F4F4F2", \
     "--theme.textColor=#3F4140"]
