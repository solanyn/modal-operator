#!/bin/bash
set -e

POD_NAME=${POD_NAME:-"unknown"}
MODALJOB_NAME="${POD_NAME}-modal"

echo "🚀 Modal execution for pod: $POD_NAME"

# Parse original containers
if [ ! -z "$ORIGINAL_IMAGES" ]; then
    echo "Original containers: $ORIGINAL_IMAGES"
else
    echo "Original image: $ORIGINAL_IMAGE"
fi

# Use operator's Modal credentials
if [ -f /etc/modal-secret/MODAL_TOKEN_ID ] && [ -f /etc/modal-secret/MODAL_TOKEN_SECRET ]; then
    export MODAL_TOKEN_ID=$(cat /etc/modal-secret/MODAL_TOKEN_ID)
    export MODAL_TOKEN_SECRET=$(cat /etc/modal-secret/MODAL_TOKEN_SECRET)
    echo "✅ Using operator's Modal credentials"
elif [ -f /etc/modal-secret/token-id ] && [ -f /etc/modal-secret/token-secret ]; then
    export MODAL_TOKEN_ID=$(cat /etc/modal-secret/token-id)
    export MODAL_TOKEN_SECRET=$(cat /etc/modal-secret/token-secret)
    echo "✅ Using operator's Modal credentials"
else
    echo "❌ Modal credentials not found"
    exit 1
fi

# Wait for ModalJob and stream logs
echo "Waiting for ModalJob $MODALJOB_NAME..."

# Unset proxy for kubectl (proxy is for workload, not API access)
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy

while true; do
    APP_ID=$(kubectl get modaljob $MODALJOB_NAME -o jsonpath='{.status.modal_app_id}' 2>/dev/null || echo "")
    if [ ! -z "$APP_ID" ] && [ "$APP_ID" != "null" ]; then
        echo "📡 Streaming logs for Modal app: $APP_ID"
        python -m modal app logs $APP_ID | python3 -c "
import sys, json
from datetime import datetime
pod_name = '$POD_NAME'
for line in sys.stdin:
    log_entry = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'pod': pod_name,
        'container': 'modal',
        'message': line.strip()
    }
    print(json.dumps(log_entry))
" || echo "Modal app completed"
        break
    fi
    sleep 2
done

echo "✅ Modal execution completed"
sleep infinity
