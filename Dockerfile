FROM alpine:latest

# Install FFmpeg, Python, and other dependencies
RUN apk add --no-cache \
    ffmpeg \
    python3 \
    py3-pip \
    bash \
    findutils

# Create working directory
WORKDIR /app

# Copy the streaming script
COPY stream_manager.py /app/
COPY start.sh /app/

# Make scripts executable
RUN chmod +x /app/start.sh

# Expose port for HTTP server
EXPOSE 8090

# Create directories for HLS output
RUN mkdir -p /app/hls

# Set the command
CMD ["/app/start.sh"]