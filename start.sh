#!/bin/bash
# Startup script for MacReplayXC + Vavoo in one container

echo "🚀 Starting MacReplayXC + Vavoo..."

# Extract public host from HOST environment variable
# HOST format: "http://your-domain.com:8001" or "0.0.0.0:8001"
if [ -n "$HOST" ]; then
    # Remove http:// or https://
    PUBLIC_HOST_CLEAN=$(echo "$HOST" | sed 's|https\?://||')
    # Extract hostname (without port)
    PUBLIC_HOSTNAME=$(echo "$PUBLIC_HOST_CLEAN" | cut -d':' -f1)
    
    export VAVOO_PUBLIC_HOST="$PUBLIC_HOSTNAME"
    export VAVOO_PORT="4323"
    
    echo "📡 Vavoo public host: $VAVOO_PUBLIC_HOST:$VAVOO_PORT"
else
    echo "⚠️  No HOST environment variable set, using auto-detection"
fi

# Start Vavoo in background
echo "📡 Starting Vavoo on port 4323..."
cd /app/vavoo
python vavoo2.py &
VAVOO_PID=$!
echo "✅ Vavoo started (PID: $VAVOO_PID)"

# Wait a moment for Vavoo to start
sleep 2

# Start MacReplayXC in foreground
echo "🎬 Starting MacReplayXC on port 8001..."
cd /app
python app.py

# If MacReplayXC exits, kill Vavoo too
kill $VAVOO_PID 2>/dev/null
