#!/bin/bash

echo "Bob Ross HLS Streamer"
echo "===================="

# Check if media directory is mounted
if [ ! -d "/media" ] || [ -z "$(ls -A /media 2>/dev/null)" ]; then
    echo "ERROR: No media directory found at /media"
    echo "Please mount your Bob Ross directory using:"
    echo "docker run -v '/path/to/your/bob/ross/directory:/media' ..."
    exit 1
fi

echo "Media directory found, starting streamer..."

# Run the Python streaming manager
python3 /app/stream_manager.py