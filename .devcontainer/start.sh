#!/usr/bin/env bash
# Starts the sample company dashboard (port 9000) and Sahaaya (port 8000) in the background.
cd "$(dirname "$0")/.."
pkill -f "uvicorn sample_dashboard.main" 2>/dev/null
pkill -f "uvicorn app.main" 2>/dev/null
nohup python -m uvicorn sample_dashboard.main:app --host 0.0.0.0 --port 9000 > /tmp/dashboard.log 2>&1 &
sleep 2
if [ -n "$CODESPACE_NAME" ]; then   # the dashboard link in the app must use the Codespaces web address
  export DEMO_DASHBOARD_PUBLIC_URL="https://${CODESPACE_NAME}-9000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}"
fi
DEMO_DASHBOARD_URL=http://127.0.0.1:9000 nohup python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/sahaaya.log 2>&1 &
echo "Sahaaya: port 8000 | company dashboard: port 9000 (see the PORTS tab). Logs: /tmp/sahaaya.log"
