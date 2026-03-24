#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$HOME/claude-monitor"
ZSHRC="$HOME/.zshrc"
SETTINGS="$HOME/.claude/settings.json"

echo "==> Claude Code Monitor installer"

# 1. Clone or update
if [ -d "$REPO_DIR/.git" ]; then
  echo "--> Updating existing clone..."
  git -C "$REPO_DIR" pull --ff-only
else
  echo "--> Cloning repository..."
  git clone "git@github.com:jakob1992/claude-monitor.git" "$REPO_DIR"
fi

# 2. Create venv and install dependencies
echo "--> Setting up Python virtual environment..."
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$REPO_DIR/.venv/bin/pip" install --quiet -r "$REPO_DIR/requirements.txt"

# 3. Configure ~/.claude/settings.json telemetry (requires jq)
if command -v jq &>/dev/null && [ -f "$SETTINGS" ]; then
  echo "--> Configuring telemetry in $SETTINGS..."
  TMP=$(mktemp)
  jq '
    .env //= {} |
    .env.CLAUDE_CODE_ENABLE_TELEMETRY = "1" |
    .env.OTEL_METRICS_EXPORTER = "prometheus" |
    .env.OTEL_EXPORTER_PROMETHEUS_PORT = "9464"
  ' "$SETTINGS" > "$TMP" && mv "$TMP" "$SETTINGS"
else
  echo "[!] jq not found or settings.json missing — add telemetry env vars manually:"
  echo '    CLAUDE_CODE_ENABLE_TELEMETRY=1'
  echo '    OTEL_METRICS_EXPORTER=prometheus'
  echo '    OTEL_EXPORTER_PROMETHEUS_PORT=9464'
fi

# 4. Add ccm alias to ~/.zshrc
CCM_ALIAS="alias ccm='source ~/claude-monitor/.venv/bin/activate && python ~/claude-monitor/monitor.py'"
if grep -qF "alias ccm=" "$ZSHRC" 2>/dev/null; then
  echo "--> ccm alias already present in $ZSHRC"
else
  echo "" >> "$ZSHRC"
  echo "# Claude Code Monitor" >> "$ZSHRC"
  echo "$CCM_ALIAS" >> "$ZSHRC"
  echo "--> Added ccm alias to $ZSHRC"
fi

echo ""
echo "Done! Open a new terminal and run: ccm"
