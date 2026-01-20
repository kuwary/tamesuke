#!/bin/bash
set -e

echo "========================================"
echo "Tamesuke Configure"
echo "========================================"

# メタデータ読み込み
METADATA_FILE="/opt/tamesuke/etc/metadata.json"

if [ ! -f "$METADATA_FILE" ]; then
    echo "[ERROR] Metadata file not found: $METADATA_FILE"
    exit 1
fi

TUNNEL_TOKEN=$(jq -r '.tunnel_token' "$METADATA_FILE")
OSS_TYPE=$(jq -r '.oss_type' "$METADATA_FILE")

echo "OSS Type: $OSS_TYPE"

# Cloudflared サービス登録
echo "Setting up Cloudflare Tunnel..."

cat > /etc/systemd/system/cloudflared.service << EOF
[Unit]
Description=cloudflared
After=network-online.target
Wants=network-online.target

[Service]
TimeoutStartSec=60
Type=notify
ExecStart=/usr/bin/cloudflared --no-autoupdate --protocol http2 tunnel run --token ${TUNNEL_TOKEN}
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable cloudflared
systemctl start cloudflared

echo "✓ Cloudflare Tunnel service started"

# サービス状態確認
systemctl status cloudflared --no-pager

echo "========================================"
echo "Configuration completed"
echo "========================================"
