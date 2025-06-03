#!/usr/bin/env python3

import os
import random
import subprocess
import threading
import time
import glob
from http.server import HTTPServer, SimpleHTTPRequestHandler
import signal
import sys
import json
import re

class StreamManager:
    def __init__(self, media_dir="/media", hls_dir="/app/hls"):
        self.media_dir = media_dir
        self.hls_dir = hls_dir
        self.current_process = None
        self.server = None
        self.running = True
        self.ffmpeg_healthy = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        print(f"Received signal {signum}, shutting down...")
        self.running = False
        if self.current_process:
            self.current_process.terminate()
        if self.server:
            self.server.shutdown()
        sys.exit(0)
    
    def find_mp4_files(self):
        """Find all MP4 files in the media directory"""
        mp4_files = []
        print(f"Scanning for MP4 files in: {self.media_dir}")
        
        for root, dirs, files in os.walk(self.media_dir):
            print(f"Checking directory: {root}")
            for file in files:
                if file.lower().endswith('.mp4'):
                    full_path = os.path.join(root, file)
                    # Check if file is readable and get size
                    try:
                        size = os.path.getsize(full_path)
                        if size > 1024 * 1024:  # At least 1MB
                            mp4_files.append(full_path)
                            print(f"  Found: {file} ({size // (1024*1024)}MB)")
                        else:
                            print(f"  Skipping small file: {file} ({size}B)")
                    except Exception as e:
                        print(f"  Error accessing {file}: {e}")
        
        return mp4_files
    
    def test_file_with_ffprobe(self, file_path):
        """Test if a file can be read by FFmpeg"""
        try:
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', '-show_streams', file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                info = json.loads(result.stdout)
                duration = float(info['format'].get('duration', 0))
                print(f"  File OK: {os.path.basename(file_path)} - Duration: {duration:.1f}s")
                return True
            else:
                print(f"  File ERROR: {os.path.basename(file_path)} - {result.stderr}")
                return False
        except Exception as e:
            print(f"  File ERROR: {os.path.basename(file_path)} - {e}")
            return False
    
    def create_playlist_file(self, mp4_files):
        """Create a playlist file for FFmpeg concat demuxer"""
        playlist_path = "/tmp/playlist.txt"
        
        # Test files first
        print("Testing files with ffprobe...")
        valid_files = []
        for i, file_path in enumerate(mp4_files):
            print(f"Testing file {i+1}/{len(mp4_files)}: {os.path.basename(file_path)}")
            if self.test_file_with_ffprobe(file_path):
                valid_files.append(file_path)
        
        if not valid_files:
            print("ERROR: No valid video files found!")
            return None
        
        print(f"Valid files: {len(valid_files)} out of {len(mp4_files)} total")
        
        # Shuffle the valid files for random order
        shuffled_files = valid_files.copy()
        random.shuffle(shuffled_files)
        
        print(f"Creating playlist with {len(shuffled_files)} files in random order...")
        print("Shuffled order (first 10 files):")
        for i, file_path in enumerate(shuffled_files[:10]):
            print(f"  {i+1:2d}. {os.path.basename(file_path)}")
        if len(shuffled_files) > 10:
            print(f"  ... and {len(shuffled_files) - 10} more files")
        
        with open(playlist_path, 'w') as f:
            for i, file_path in enumerate(shuffled_files):
                # Escape single quotes and backslashes for FFmpeg
                escaped_path = file_path.replace("'", "'\"'\"'").replace("\\", "\\\\")
                f.write(f"file '{escaped_path}'\n")
                # Add a comment for debugging
                f.write(f"# {i+1}. {os.path.basename(file_path)}\n")
        
        # Show playlist content (just first few entries)
        print("\nPlaylist file contents (first 20 lines):")
        with open(playlist_path, 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines[:20]):
                print(f"  {line.strip()}")
            if len(lines) > 20:
                print(f"  ... and {len(lines) - 20} more lines")
        
        return playlist_path
    
    def cleanup_hls_files(self):
        """Clean up existing HLS files"""
        print("Cleaning up existing HLS files...")
        files_removed = 0
        for pattern in ["*.ts", "*.m3u8"]:
            for f in glob.glob(f"{self.hls_dir}/{pattern}"):
                try:
                    os.remove(f)
                    files_removed += 1
                except Exception as e:
                    print(f"Error removing {f}: {e}")
        print(f"Removed {files_removed} old HLS files")
    
    def start_streaming(self):
        """Start the HLS streaming process"""
        mp4_files = self.find_mp4_files()
        
        if not mp4_files:
            print(f"ERROR: No MP4 files found in {self.media_dir}")
            return False
        
        print(f"Found {len(mp4_files)} MP4 files")
        
        # Create randomized playlist
        playlist_path = self.create_playlist_file(mp4_files)
        if not playlist_path:
            return False
        
        # Ensure HLS directory exists and is clean
        os.makedirs(self.hls_dir, exist_ok=True)
        self.cleanup_hls_files()
        
        # Simple FFmpeg command - let's start basic and build up
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'info',
            '-re',  # Read input at native frame rate
            '-f', 'concat',
            '-safe', '0',
            '-stream_loop', '-1',  # Loop infinitely
            '-i', playlist_path,
            # Video encoding
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Fastest encoding
            '-tune', 'zerolatency',
            '-crf', '28',  # Higher CRF for faster encoding
            '-g', '30',  # Keyframe every 30 frames
            '-keyint_min', '30',
            '-sc_threshold', '0',
            # Audio encoding
            '-c:a', 'aac',
            '-b:a', '96k',
            '-ar', '44100',
            # HLS output
            '-f', 'hls',
            '-hls_time', '4',  # 4 second segments
            '-hls_list_size', '12',  # Keep 12 segments (48 seconds buffer)
            '-hls_flags', 'delete_segments+independent_segments',
            '-hls_segment_type', 'mpegts',
            '-hls_allow_cache', '0',
            '-start_number', '1',
            '-hls_segment_filename', f'{self.hls_dir}/stream%d.ts',
            f'{self.hls_dir}/stream.m3u8'
        ]
        
        print("="*60)
        print("STARTING FFMPEG STREAM")
        print("="*60)
        print("Command:")
        print(" ".join(ffmpeg_cmd))
        print("="*60)
        
        try:
            self.current_process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Start monitoring thread
            threading.Thread(target=self.monitor_ffmpeg, daemon=True).start()
            
            return True
        except Exception as e:
            print(f"CRITICAL ERROR starting FFmpeg: {e}")
            return False

    def monitor_ffmpeg(self):
        bad_file = None
        current_file = None

        # Pattern to match the file currently being played
        concat_file_re = re.compile(r"Opening '(.*)' for reading")
        error_detected = False

        for line in self.current_process.stdout:
            print("FFmpeg:", line.strip())

            # Detect file being processed (assumes verbose FFmpeg logs are enabled)
            match = concat_file_re.search(line)
            if match:
                current_file = match.group(1)

            # Detect critical decoder errors
            if 'Error submitting packet to decoder' in line or \
               'Decoder thread returned error' in line or \
               'Internal bug, should not have happened' in line:
                error_detected = True
                bad_file = current_file
                print("FFmpeg ERROR: Detected critical decode issue!")
                break

        if error_detected:
            self.handle_ffmpeg_crash(bad_file)

    def handle_ffmpeg_crash(self, bad_file):
        print(f"Handling FFmpeg crash due to bad file: {bad_file}")

        # Kill ffmpeg process
        if self.current_process:
            self.current_process.kill()
            self.current_process.wait()

        # Log bad file
        if bad_file:
            with open('naughty_list.txt', 'a') as f:
                f.write(f"{bad_file}\n")

            # Optionally remove or comment the bad file from the playlist
            #self.remove_from_playlist(bad_file)

        # Restart your stream logic
        time.sleep(1)  # Brief delay to avoid rapid restart loops
        print("Restarting main()...")
        self.run()

    def handle_ffmpeg_crash(self, bad_file):
        print(f"Handling FFmpeg crash due to bad file: {bad_file}")

        # Kill ffmpeg process
        if self.current_process:
            self.current_process.kill()
            self.current_process.wait()

        # Log bad file
        if bad_file:
            with open('naughty_list.txt', 'a') as f:
                f.write(f"{bad_file}\n")

            # Optionally remove or comment the bad file from the playlist
            #self.remove_from_playlist(bad_file)

        # Restart your stream logic
        time.sleep(1)  # Brief delay to avoid rapid restart loops
        print("Restarting main()...")
        self.run()  
        
    def remove_from_playlist(self, bad_file):
        try:
            with open(self.playlist_path, 'r') as f:
                lines = f.readlines()
            with open(self.playlist_path, 'w') as f:
                for line in lines:
                    if bad_file not in line:
                        f.write(line)
                    else:
                        print(f"Removed bad file from playlist: {bad_file}")
        except Exception as e:
            print(f"Error updating playlist: {e}")

    def debug_monitor_ffmpeg(self):
        """Monitor FFmpeg output with detailed logging"""
        if not self.current_process:
            return
            
        print("FFmpeg monitoring started...")
        line_count = 0
        last_progress_time = 0
        current_file = None
        
        try:
            while self.running and self.current_process.poll() is None:
                line = self.current_process.stdout.readline()
                if not line:
                    continue
                    
                line = line.strip()
                line_count += 1
                
                # Always print first 20 lines for startup info
                if line_count <= 20:
                    print(f"FFmpeg[{line_count:02d}]: {line}")
                    continue
                
                # Look for important messages
                lower_line = line.lower()
                if any(keyword in lower_line for keyword in ['error', 'failed', 'invalid', 'could not']):
                    print(f"FFmpeg ERROR: {line}")
                    self.ffmpeg_healthy = False
                    if 'parsing' in lower_line:
                        with open('naughty_list.txt', a) as file:
                            file.write(f'{current_file}\n')
                        main()
                elif any(keyword in lower_line for keyword in ['warning']):
                    print(f"FFmpeg WARNING: {line}")
                elif 'opening' in lower_line and 'for reading' in lower_line:
                    # Extract filename from the line
                    if "'" in line:
                        filename = line.split("'")[1] if "'" in line else "unknown"
                        basename = os.path.basename(filename)
                        if basename != current_file:
                            current_file = basename
                            print(f"FFmpeg NOW PLAYING: {basename}")
                    print(f"FFmpeg FILE: {line}")
                elif 'frame=' in line and 'fps=' in line:
                    # Print progress every 30 seconds and include current file
                    current_time = time.time()
                    if current_time - last_progress_time >= 30:
                        progress_info = line
                        if current_file:
                            progress_info += f" | Playing: {current_file}"
                        print(f"FFmpeg PROGRESS: {progress_info}")
                        last_progress_time = current_time
                        self.ffmpeg_healthy = True
                elif 'hls' in lower_line:
                    print(f"FFmpeg HLS: {line}")
                elif 'input #0' in lower_line and 'from' in lower_line:
                    # This shows when FFmpeg switches to a new input file
                    print(f"FFmpeg INPUT: {line}")
                    
        except Exception as e:
            print(f"Error in FFmpeg monitoring: {e}")
        
        # Check if FFmpeg exited
        if self.current_process and self.current_process.poll() is not None:
            return_code = self.current_process.returncode
            print(f"FFmpeg process exited with code: {return_code}")
            if return_code != 0:
                print("FFmpeg failed! This explains the streaming issues.")
    
    def monitor_hls_files(self):
        """Monitor HLS file generation"""
        print("Starting HLS file monitoring...")
        last_segment_count = 0
        last_playlist_size = 0
        
        while self.running:
            try:
                # Count segments
                segments = glob.glob(f"{self.hls_dir}/*.ts")
                segment_count = len(segments)
                
                # Check playlist
                playlist_path = f"{self.hls_dir}/stream.m3u8"
                playlist_size = 0
                if os.path.exists(playlist_path):
                    playlist_size = os.path.getsize(playlist_path)
                
                # Report if changed
                if segment_count != last_segment_count or playlist_size != last_playlist_size:
                    print(f"HLS Status: {segment_count} segments, playlist {playlist_size} bytes")
                    
                    if segment_count > 0:
                        # Show latest segment info
                        latest_segment = max(segments, key=os.path.getctime)
                        segment_size = os.path.getsize(latest_segment)
                        print(f"  Latest segment: {os.path.basename(latest_segment)} ({segment_size} bytes)")
                    
                    last_segment_count = segment_count
                    last_playlist_size = playlist_size
                
                time.sleep(5)
                
            except Exception as e:
                print(f"Error monitoring HLS files: {e}")
                time.sleep(5)
    
    def start_http_server(self):
        """Start HTTP server to serve HLS files"""
        os.chdir(self.hls_dir)
        
        class CORSHandler(SimpleHTTPRequestHandler):
            def end_headers(self):
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                super().end_headers()
            
            def log_message(self, format, *args):
                # Custom logging format
                print(f"HTTP: {self.client_address[0]} - {format % args}")
        
        self.server = HTTPServer(('0.0.0.0', 8090), CORSHandler)
        print("HTTP server starting on port 8090...")
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("HTTP server interrupted")
        except Exception as e:
            print(f"HTTP server error: {e}")
    
    def run(self):
        """Main run method"""
        print("Bob Ross HLS Streamer Starting...")
        print(f"Media directory: {self.media_dir}")
        print(f"HLS output directory: {self.hls_dir}")
        
        # Start streaming
        if not self.start_streaming():
            print("FAILED to start streaming - exiting")
            return
        
        # Start HLS file monitoring
        threading.Thread(target=self.monitor_hls_files, daemon=True).start()
        
        print("Waiting for FFmpeg to initialize and create first segments...")
        # Wait longer for initialization
        for i in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            if os.path.exists(f"{self.hls_dir}/stream.m3u8"):
                print(f"Stream playlist created after {i+1} seconds")
                break
            if i % 5 == 4:  # Every 5 seconds
                print(f"Still waiting for stream initialization... ({i+1}s)")
        
        # Check final status
        stream_file = f"{self.hls_dir}/stream.m3u8"
        if os.path.exists(stream_file):
            try:
                with open(stream_file, 'r') as f:
                    content = f.read()
                print("="*50)
                print("INITIAL PLAYLIST CONTENT:")
                print("="*50)
                print(content)
                print("="*50)
            except Exception as e:
                print(f"Error reading stream file: {e}")
        else:
            print("CRITICAL: Stream file was never created!")
            print("This indicates FFmpeg is not working properly.")
            if self.current_process:
                print(f"FFmpeg process status: {self.current_process.poll()}")
            return
        
        segments = glob.glob(f"{self.hls_dir}/*.ts")
        print(f"Found {len(segments)} initial segments")
        
        print("="*60)
        print("STREAM READY!")
        print(f"Access your stream at: http://YOUR_IP:8090/stream.m3u8")
        print("="*60)
        
        # Start HTTP server (this will block)
        self.start_http_server()

def main():
    manager = StreamManager()
    manager.run()

if __name__ == "__main__":
    main()
    