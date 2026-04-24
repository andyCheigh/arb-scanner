#!/usr/bin/env bash
# Deploy arb-scanner to a remote Linux host via SSH + run it under systemd.
#
# Usage:   ./deploy.sh user@host [remote-path]
# Example: ./deploy.sh ubuntu@my-devbox.example.com
#          ./deploy.sh ubuntu@1.2.3.4 /opt/arb-scanner
#
# Idempotent: re-run any time to push new code + restart the service.

set -euo pipefail

REMOTE="${1:?usage: ./deploy.sh user@host [remote-path]}"
REMOTE_USER="$(echo "$REMOTE" | cut -d@ -f1)"
REMOTE_PATH="${2:-/home/${REMOTE_USER}/arb-scanner}"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -f "$LOCAL_DIR/.env" ]]; then
  echo "ERROR: $LOCAL_DIR/.env not found. Create it from .env.example first."
  exit 1
fi

echo "→ Syncing code to $REMOTE:$REMOTE_PATH"
rsync -az --delete \
  --exclude='.venv/' \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='state/' \
  --exclude='*.log' \
  --exclude='*.pyc' \
  "$LOCAL_DIR/" "$REMOTE:$REMOTE_PATH/"

echo "→ Installing deps in venv on remote"
ssh "$REMOTE" bash -s <<REMOTE_SETUP
set -euo pipefail
cd "$REMOTE_PATH"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
REMOTE_SETUP

echo "→ Installing systemd unit (sudo required on remote)"
ssh "$REMOTE" "sudo tee /etc/systemd/system/arb-scanner.service >/dev/null" <<UNIT
[Unit]
Description=Arb Scanner — sportsbook arbitrage alert bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$REMOTE_USER
WorkingDirectory=$REMOTE_PATH
EnvironmentFile=$REMOTE_PATH/.env
ExecStart=$REMOTE_PATH/.venv/bin/python -u main.py
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT

echo "→ Reloading systemd + (re)starting service"
ssh "$REMOTE" "sudo systemctl daemon-reload && sudo systemctl enable arb-scanner && sudo systemctl restart arb-scanner"

echo "→ Status:"
ssh "$REMOTE" "sudo systemctl status arb-scanner --no-pager -l | head -12 || true"

cat <<EOF

✓ Deployed to $REMOTE:$REMOTE_PATH

Useful commands (run locally):
  ssh $REMOTE 'sudo journalctl -u arb-scanner -f'      # tail logs
  ssh $REMOTE 'sudo journalctl -u arb-scanner -n 100'  # last 100 lines
  ssh $REMOTE 'sudo systemctl restart arb-scanner'     # restart
  ssh $REMOTE 'sudo systemctl stop arb-scanner'        # stop
  ssh $REMOTE 'sudo systemctl status arb-scanner'      # status

Re-deploy code changes:
  ./deploy.sh $REMOTE
EOF
