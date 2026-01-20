#!/bin/bash
set -e

# hostnameを取得（subdomainと同じ）
HOSTNAME=$(hostname)

echo "========================================"
echo "Tamesuke Init: HOSTNAME=${HOSTNAME}"
echo "========================================"

mkdir -p /opt/tamesuke/etc

MAX_RETRIES=10
RETRY_COUNT=0
RETRY_INTERVAL=3

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Attempting to download metadata (${RETRY_COUNT}/${MAX_RETRIES})..."
    
    if curl -f -s --connect-timeout 5 \
       "http://fileserver:8080/metadata/metadata-${HOSTNAME}.json" \
       -o /opt/tamesuke/etc/metadata.json; then
        echo "✓ Metadata downloaded successfully"
        
        echo "Metadata contents:"
        cat /opt/tamesuke/etc/metadata.json
        echo ""
        
        if [ -x /opt/tamesuke/bin/tamesuke-configure.sh ]; then
            echo "Running configuration script..."
            /opt/tamesuke/bin/tamesuke-configure.sh
        fi
        
        echo "✓ Initialization completed"
        exit 0
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        echo "Retry in ${RETRY_INTERVAL}s..."
        sleep $RETRY_INTERVAL
    fi
done

echo "✗ ERROR: Failed to download metadata after $MAX_RETRIES attempts"
exit 1
