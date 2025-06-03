# Shuffle HLS Streamer

A Docker container that streams any mp4 episodes as an HLS stream for any device that can subscribe to a .m3u8 stream.

## Features

- Automatically finds all MP4 files in subdirectories
- Streams episodes in random order
- Loops infinitely - when all episodes are played, it shuffles and starts over
- Serves HLS stream on port 8090
- CORS enabled for web/TV app compatibility

## Quick Start

**Build and run with Docker Compose:**
   ```bash
   docker-compose up -d
   ```


## Accessing the Stream

You can access your stream at:
```
http://{your_server_ip}:8090/stream.m3u8
```

Replace `{your_server_ip}` with the IP address of the machine running the Docker container.

You can test this in VLC by going to Media > Open Network Stream and inputing that address ^

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

1. **No video files found:** Make sure your Show's directory is properly mounted to /media in the container
2. **Stream not accessible:** Check firewall settings and ensure port 8090 is open
