# syntax=docker/dockerfile:1

# ────────────────────────────────────────────────────────────────────────────
# Stage 1: Install the official Kiro CLI
#
# The Kiro CLI is installed from the official installer (https://cli.kiro.dev/
# install) so the image is self-contained — no need to bind-mount the binary
# at runtime. The installer downloads the signed, checksum-verified Linux build
# of `kiro-cli` / `kiro-cli-chat` (the ACP agent) into ~/.local/bin.
#
# Pin a channel with --build-arg KIRO_CHANNEL=stable (default).
#
# NOTE: the resulting image contains the proprietary Kiro CLI. That is fine for
# your own/local images; do not redistribute the image publicly unless the Kiro
# CLI license permits it.
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.14-slim AS kiro-installer

ARG KIRO_CHANNEL=stable

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install into a throwaway HOME, then promote the binaries to /usr/local/bin.
RUN export HOME=/opt/kiro-install && mkdir -p "$HOME" \
    && curl -fsSL https://cli.kiro.dev/install | bash -s -- --channel "${KIRO_CHANNEL}" \
    && install -m 0755 "$HOME/.local/bin/kiro-cli"      /usr/local/bin/kiro-cli \
    && install -m 0755 "$HOME/.local/bin/kiro-cli-chat" /usr/local/bin/kiro-cli-chat \
    && /usr/local/bin/kiro-cli-chat --version

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
      org.opencontainers.image.description="ACP-compliant bridge: OpenAI/Anthropic API → kiro CLI" \
      org.opencontainers.image.source="https://github.com/ankitcharolia/kiro-gateway" \
      org.opencontainers.image.licenses="AGPL-3.0"

# ca-certificates is needed for the Kiro CLI's outbound TLS calls.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Bundle the official Kiro CLI (real binary, not a stub).
COPY --from=kiro-installer /usr/local/bin/kiro-cli      /usr/local/bin/kiro-cli
COPY --from=kiro-installer /usr/local/bin/kiro-cli-chat /usr/local/bin/kiro-cli-chat

# Copy installed Python packages
COPY --from=builder /install /usr/local

WORKDIR /app
COPY . .

# The gateway never needs root. A world-writable HOME lets the container run as
# an arbitrary host uid (recommended: --user "$(id -u):$(id -g)") so it can read
# the bind-mounted credentials AND write the per-user runtime state the Kiro CLI
# creates on first use (~/.local/share/kiro-cli: token-refresh state + helpers).
RUN useradd --no-create-home --shell /bin/false gateway && \
    mkdir -p /home/gateway && chmod 0777 /home/gateway && \
    chown -R gateway:gateway /app
USER gateway

# Only credentials are mounted at runtime (read-write — the token in
# ~/.aws/sso/cache is refreshed in place and session files are written to
# ~/.kiro):
#   -v ~/.aws:/home/gateway/.aws  -v ~/.kiro:/home/gateway/.kiro
# KIRO_CLI_PATH points at the bundled ACP agent (kiro-cli-chat).
ENV HOME=/home/gateway \
    KIRO_CLI_PATH=/usr/local/bin/kiro-cli-chat \
    ACP_TRUST_TOOLS=false \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "main.py"]
