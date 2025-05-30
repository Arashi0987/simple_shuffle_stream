# Bob Ross HLS Streamer

A Docker container that streams Bob Ross "The Joy of Painting" episodes as an HLS stream for your Tizen TV app.

## Features

- Automatically finds all MP4 files in subdirectories
- Streams episodes in random order
- Loops infinitely - when all episodes are played, it shuffles and starts over
- Serves HLS stream on port 8090
- CORS enabled for web/TV app compatibility

## Quick Start

1. **Build and run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

2. **Or run with Docker directly:**
   ```bash
   # Build the image
   docker build -t bob-ross-streamer .
   
   # Run the container
   docker run -d \
     --name bob-ross-streamer \
     -p 8090:8090 \
     -v "/Media/TV_Shows/Real_Shows/Bob Ross The Joy of Painting:/media:ro" \
     bob-ross-streamer
   ```

## Accessing the Stream

Your Tizen TV app can access the stream at:
```
http://{your_server_ip}:8090/stream.m3u8
```

Replace `{your_server_ip}` with the IP address of the machine running the Docker container.

## File Structure

Place your files in this structure:
```
docker-streamer/
├── Dockerfile
├── docker-compose.yml
├── stream_manager.py
├── start.sh
└── README.md
```

## Configuration

The container automatically:
- Scans for all `.mp4` files in mounted directory and subdirectories
- Creates HLS segments with 10-second duration
- Maintains a 6-segment sliding window
- Streams at 2Mbps max bitrate with 128k audio

## Monitoring

Check container logs:
```bash
docker logs bob-ross-streamer -f
```

Check if stream is working:
```bash
curl http://localhost:8090/stream.m3u8
```

## Troubleshooting

1. **No video files found:** Make sure your Bob Ross directory is properly mounted
2. **Stream not accessible:** Check firewall settings and ensure port 8090 is open
3. **Playback issues:** Verify your Tizen app supports HLS streams

## Stopping the Service

```bash
# With docker-compose
docker-compose down

# With docker directly
docker stop bob-ross-streamer
docker rm bob-ross-streamer
```