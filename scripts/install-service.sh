#!/usr/bin/env bash
# install-service.sh — install kiro-gateway as a background service
#
# Supports:
#   Linux  — systemd user service (recommended, no sudo required)
#   macOS  — launchd user agent (no sudo required)
#
# Usage:
#   bash scripts/install-service.sh            # install
#   bash scripts/install-service.sh --uninstall  # remove
#
# The script auto-detects the repo root and venv paths. Run it from
# anywhere inside the repository checkout.

set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────────────────────
info()  { printf '\033[0;34m[info]\033[0m  %s\n' "$*"; }
ok()    { printf '\033[0;32m[ ok ]\033[0m  %s\n' "$*"; }
warn()  { printf '\033[0;33m[warn]\033[0m  %s\n' "$*"; }
die()   { printf '\033[0;31m[err ]\033[0m  %s\n' "$*" >&2; exit 1; }

UNINSTALL=false
for arg in "$@"; do
  [[ "$arg" == "--uninstall" ]] && UNINSTALL=true
done

# ── Locate the repository root ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
ENV_FILE="$REPO_ROOT/.env"

info "Repository root : $REPO_ROOT"

# ── Sanity checks (skip on uninstall) ─────────────────────────────────────────
if [[ "$UNINSTALL" == false ]]; then
  [[ -f "$REPO_ROOT/main.py" ]] || die "main.py not found in $REPO_ROOT — are you inside the kiro-gateway repo?"
  [[ -f "$VENV_PYTHON" ]]       || die ".venv not found. Run: uv sync"
  [[ -f "$ENV_FILE" ]]          || die ".env not found. Run: cp .env.example .env  (then set KIRO_GATEWAY_API_KEY)"
  grep -q "^KIRO_GATEWAY_API_KEY=" "$ENV_FILE" || warn ".env does not contain KIRO_GATEWAY_API_KEY — the gateway will start but auth will fall back to the default test key."
fi

# ═════════════════════════════════════════════════════════════════════════════
# Linux — systemd user service
# ═════════════════════════════════════════════════════════════════════════════
install_linux() {
  local unit_dir="$HOME/.config/systemd/user"
  local unit_file="$unit_dir/kiro-gateway.service"
  mkdir -p "$unit_dir"

  info "Writing $unit_file"
  cat > "$unit_file" <<EOF
[Unit]
Description=Kiro Gateway — ACP-compliant OpenAI/Anthropic bridge for kiro-cli
Documentation=https://github.com/ankitcharolia/kiro-gateway
After=network.target

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT
ExecStart=$VENV_PYTHON $REPO_ROOT/main.py
EnvironmentFile=$ENV_FILE
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kiro-gateway

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable --now kiro-gateway
  ok "Service installed and started."
  info "Status  : systemctl --user status kiro-gateway"
  info "Logs    : journalctl --user -u kiro-gateway -f"
  info "Stop    : systemctl --user stop kiro-gateway"
  info "Disable : systemctl --user disable kiro-gateway"
}

uninstall_linux() {
  local unit_file="$HOME/.config/systemd/user/kiro-gateway.service"
  if systemctl --user is-active --quiet kiro-gateway 2>/dev/null; then
    systemctl --user stop kiro-gateway
    ok "Service stopped."
  fi
  systemctl --user disable kiro-gateway 2>/dev/null || true
  [[ -f "$unit_file" ]] && rm "$unit_file" && ok "Removed $unit_file"
  systemctl --user daemon-reload
  ok "Service removed."
}

# ═════════════════════════════════════════════════════════════════════════════
# macOS — launchd user agent
# ═════════════════════════════════════════════════════════════════════════════
install_macos() {
  local agents_dir="$HOME/Library/LaunchAgents"
  local plist_file="$agents_dir/com.kiro.gateway.plist"
  mkdir -p "$agents_dir"

  # Read KIRO_GATEWAY_API_KEY from .env (strip quotes/whitespace)
  local api_key
  api_key=$(grep "^KIRO_GATEWAY_API_KEY=" "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" | xargs)
  [[ -z "$api_key" ]] && api_key="change-me"

  info "Writing $plist_file"
  cat > "$plist_file" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kiro.gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>$VENV_PYTHON</string>
        <string>$REPO_ROOT/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO_ROOT</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>KIRO_GATEWAY_API_KEY</key>
        <string>$api_key</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/kiro-gateway.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/kiro-gateway.stderr.log</string>
</dict>
</plist>
EOF

  launchctl load -w "$plist_file"
  ok "Agent installed and started."
  info "Status  : launchctl list | grep kiro"
  info "Logs    : tail -f /tmp/kiro-gateway.stdout.log"
  info "Stop    : launchctl unload $plist_file"
}

uninstall_macos() {
  local plist_file="$HOME/Library/LaunchAgents/com.kiro.gateway.plist"
  if launchctl list | grep -q "com.kiro.gateway" 2>/dev/null; then
    launchctl unload "$plist_file" 2>/dev/null || true
    ok "Agent unloaded."
  fi
  [[ -f "$plist_file" ]] && rm "$plist_file" && ok "Removed $plist_file"
  ok "Service removed."
}

# ═════════════════════════════════════════════════════════════════════════════
# Dispatch
# ═════════════════════════════════════════════════════════════════════════════
OS="$(uname -s)"
case "$OS" in
  Linux)
    command -v systemctl &>/dev/null || die "systemctl not found — systemd is required."
    if [[ "$UNINSTALL" == true ]]; then uninstall_linux; else install_linux; fi
    ;;
  Darwin)
    if [[ "$UNINSTALL" == true ]]; then uninstall_macos; else install_macos; fi
    ;;
  *)
    die "Unsupported OS: $OS. Only Linux (systemd) and macOS (launchd) are supported."
    ;;
esac
