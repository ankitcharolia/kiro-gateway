# syntax=docker/dockerfile:1

# ────────────────────────────────────────────────────────────────────────────
# Stage 1: kiro CLI placeholder
#
# The kiro CLI binary is NOT distributed as a public tarball on kiro.dev.
# Provide the binary at build time via one of these methods:
#
#   Option A – build-arg path to a local binary:
#     docker build --build-arg KIRO_BINARY=./kiro-linux-x86_64 -t kiro-gateway .
#
#   Option B – mount a pre-downloaded binary in CI:
#     docker build --secret id=kiro,src=./kiro -t kiro-gateway .
#
#   Option C (runtime-only) – bind-mount the host binary:
#     docker run -v $(which kiro):/usr/local/bin/kiro:ro kiro-gateway
#
# The stub below satisfies the COPY --from step so the image builds even
# when no real binary is provided; the gateway will fail at runtime if kiro
# is actually needed and no real binary is mounted.
# ────────────────────────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS kiro-downloader

ARG TARGETARCH
ARG KIRO_BINARY=""

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# If a local binary path is provided via --build-arg KIRO_BINARY=<path>,
# it will be COPYed in the next step.  Otherwise we create a stub that
# prints a helpful error at runtime so the build never fails with a 404.
RUN mkdir -p /usr/local/bin

# Try to copy a real binary if KIRO_BINARY was supplied; fall through to stub.
COPY ${KIRO_BINARY:-docker/kiro-stub.sh} /tmp/kiro-candidate
RUN if [ -s /tmp/kiro-candidate ] && file /tmp/kiro-candidate 2>/dev/null | grep -q 'ELF'; then \
        cp /tmp/kiro-candidate /usr/local/bin/kiro; \
    else \
        printf '#!/bin/sh\necho "kiro binary not installed. Mount the real kiro binary at /usr/local/bin/kiro" >&2\nexit 1\n' > /usr/local/bin/kiro; \
    fi; \
    chmod +x /usr/local/bin/kiro

# ────────────────────────────────────────────────────────────────────────────
# Stage 2: Python dependency build
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ────────────────────────────────────────────────────────────────────────────
# Stage 3: Runtime image
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

LABEL org.opencontainers.image.title="kiro-gateway" \
      org.opencontainers.image.description="ACP-compliant bridge: OpenAI/Anthropic API \u2192 kiro CLI" \
      org.opencontainers.image.source="https://github.com/ankitcharolia/kiro-gateway" \
      org.opencontainers.image.licenses="AGPL-3.0"

# Copy kiro CLI (real or stub) from downloader stage
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
