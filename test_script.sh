#!/bin/bash

echo "Testing Bob Ross HLS Stream"
echo "=========================="

SERVER_IP=${1:-localhost}
STREAM_URL="http://${SERVER_IP}:8090/stream.m3u8"

echo "Testing stream at: $STREAM_URL"
echo ""

# Test 1: Check if stream.m3u8 exists and is accessible
echo "1. Testing playlist accessibility..."
curl -s -I "$STREAM_URL" | head -1
echo ""

# Test 2: Show playlist content
echo "2. Playlist content:"
curl -s "$STREAM_URL" | head -20
echo ""
echo "=========================="

# Test 3: Check if segments are being generated
echo "3. Testing segment accessibility..."
SEGMENT=$(curl -s "$STREAM_URL" | grep -E "stream[0-9]+\.ts" | head -1)
if [ ! -z "$SEGMENT" ]; then
    SEGMENT_URL="http://${SERVER_IP}:8090/$SEGMENT"
    echo "Testing segment: $SEGMENT_URL"
    curl -s -I "$SEGMENT_URL" | head -1
    echo "Segment size: $(curl -s "$SEGMENT_URL" | wc -c) bytes"
else
    echo "No segments found in playlist"
fi
echo ""

# Test 4: VLC command
echo "4. To test with VLC, run:"
echo "vlc $STREAM_URL"
echo ""

# Test 5: FFplay command
echo "5. To test with ffplay, run:"
echo "ffplay $STREAM_URL"