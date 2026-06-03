# syntax=docker/dockerfile:1

# ────────────────────────────────────────────────────────────────────────────
# Stage 1: download the official kiro CLI binary
# ────────────────────────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS kiro-downloader

ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download the correct kiro CLI binary for the target architecture.
# Replace the URL pattern below if Kiro publishes binaries at a different path.
RUN set -eux; \
    case "${TARGETARCH}" in \
        amd64) KIRO_ARCH="x86_64" ;; \
        arm64) KIRO_ARCH="aarch64" ;; \
        *) echo "Unsupported arch: ${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fsSL \
        "https://kiro.dev/releases/latest/kiro-linux-${KIRO_ARCH}.tar.gz" \
        -o /tmp/kiro.tar.gz; \
    tar -xzf /tmp/kiro.tar.gz -C /usr/local/bin --strip-components=1 kiro; \
    chmod +x /usr/local/bin/kiro

# ────────────────────────────────────────────────────────────────────────────
# Stage 2: Python dependency build
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ────────────────────────────────────────────────────────────────────────────
# Stage 3: Runtime image
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="kiro-gateway" \
      org.opencontainers.image.description="ACP-compliant bridge: OpenAI/Anthropic API → kiro CLI" \
      org.opencontainers.image.source="https://github.com/ankitcharolia/kiro-gateway" \
      org.opencontainers.image.licenses="AGPL-3.0"

# Copy kiro CLI from downloader stage
COPY --from=kiro-downloader /usr/local/bin/kiro /usr/local/bin/kiro

# Copy installed Python packages
COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

# The gateway never needs root after startup
RUN useradd --no-create-home --shell /bin/false gateway && \
    chown -R gateway:gateway /app
USER gateway

# Kiro credentials are mounted at runtime via -v ~/.kiro:/home/gateway/.kiro:ro
# The HOME override makes kiro CLI find its tokens in the right place
ENV HOME=/home/gateway \
    KIRO_CLI_COMMAND=/usr/local/bin/kiro \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "main.py"]
