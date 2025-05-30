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
import shutil

class DynamicStreamManager:
    def __init__(self, media_dir="/media", hls_dir="/app/hls"):
        self.media_dir = media_dir
        self.hls_dir = hls_dir
        self.current_process = None
        self.server = None
        self.running = True
        self.valid_files = []
        self.current_episode_index = 0
        self.episode_history = []
        
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
    
    def find_and_validate_files(self):
        """Find and validate all MP4 files"""
        print(f"Scanning for MP4 files in: {self.media_dir}")
        
        mp4_files = []
        for root, dirs, files in os.walk(self.media_dir):
            for file in files:
                if file.lower().endswith('.mp4'):
                    full_path = os.path.join(root, file)
                    try:
                        size = os.path.getsize(full_path)
                        if size > 1024 * 1024:  # At least 1MB
                            mp4_files.append(full_path)
                    except Exception as e:
                        print(f"Error accessing {file}: {e}")
        
        print(f"Found {len(mp4_files)} MP4 files. Testing with ffprobe...")
        
        valid_files = []
        for i, file_path in enumerate(mp4_files):
            print(f"Testing {i+1}/{len(mp4_files)}: {os.path.basename(file_path)}")
            if self.test_file_with_ffprobe(file_path):
                valid_files.append(file_path)
            
        print(f"Valid files: {len(valid_files)} out of {len(mp4_files)}")
        self.valid_files = valid_files
        return len(valid_files) > 0
    
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
                if duration > 60:  # At least 1 minute
                    return True
                else:
                    print(f"  Skipping short file: {os.path.basename(file_path)} ({duration:.1f}s)")
                    return False
            else:
                print(f"  Invalid file: {os.path.basename(file_path)}")
                return False
        except Exception as e:
            print(f"  Error testing file: {os.path.basename(file_path)} - {e}")
            return False
    
    def get_next_episode(self):
        """Get the next episode to play, ensuring good shuffling"""
        if not self.valid_files:
            return None
            
        # If we've played all episodes, reshuffle
        if self.current_episode_index >= len(self.valid_files):
            print("Reshuffling episodes for new cycle...")
            random.shuffle(self.valid_files)
            self.current_episode_index = 0
            self.episode_history.clear()
        
        # Get next episode
        next_episode = self.valid_files[self.current_episode_index]
        self.current_episode_index += 1
        self.episode_history.append(os.path.basename(next_episode))
        
        print(f"Next episode ({self.current_episode_index}/{len(self.valid_files)}): {os.path.basename(next_episode)}")
        
        return next_episode
    
    def stream_single_episode(self, episode_path):
        """Stream a single episode to HLS"""
        print(f"Starting stream for: {os.path.basename(episode_path)}")
        
        # Clean up old segments but keep playlist
        for f in glob.glob(f"{self.hls_dir}/stream*.ts"):
            try:
                os.remove(f)
            except:
                pass
        
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'warning',
            '-re',  # Read at native frame rate
            '-i', episode_path,
            # Video encoding
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '26',
            '-g', '60',  # Keyframe every 2 seconds at 30fps
            '-keyint_min', '60',
            '-sc_threshold', '0',
            # Audio encoding
            '-c:a', 'aac',
            '-b:a', '128k',
            '-ar', '44100',
            # HLS output
            '-f', 'hls',
            '-hls_time', '6',
            '-hls_list_size', '10',
            '-hls_flags', 'independent_segments',
            '-hls_segment_type', 'mpegts',
            '-hls_allow_cache', '0',
            '-hls_segment_filename', f'{self.hls_dir}/stream%d.ts',
            f'{self.hls_dir}/stream.m3u8'
        ]
        
        try:
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # Wait for process to complete or for us to stop
            while self.running and process.poll() is None:
                time.sleep(1)
            
            if process.poll() is None:
                process.terminate()
                process.wait()
            
            return_code = process.returncode
            if return_code != 0:
                stderr = process.stderr.read()
                print(f"FFmpeg error for {os.path.basename(episode_path)}: {stderr}")
                return False
            else:
                print(f"Completed streaming: {os.path.basename(episode_path)}")
                return True
                
        except Exception as e:
            print(f"Error streaming {os.path.basename(episode_path)}: {e}")
            return False
    
    def continuous_streaming_loop(self):
        """Continuously stream episodes one after another"""
        print("Starting continuous streaming loop...")
        
        # Shuffle the initial list
        random.shuffle(self.valid_files)
        print("Initial shuffle complete.")
        print("Episode order for this cycle:")
        for i, file_path in enumerate(self.valid_files[:10]):
            print(f"  {i+1:2d}. {os.path.basename(file_path)}")
        if len(self.valid_files) > 10:
            print(f"  ... and {len(self.valid_files) - 10} more")
        
        while self.running:
            episode = self.get_next_episode()
            if not episode:
                print("No episodes available!")
                time.sleep(30)
                continue
            
            success = self.stream_single_episode(episode)
            if not success:
                print(f"Failed to stream {os.path.basename(episode)}, trying next...")
                time.sleep(5)  # Brief pause before trying next episode
            
            # Small gap between episodes
            if self.running:
                time.sleep(2)
    
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
                print(f"HTTP: {self.client_address[0]} - {format % args}")
        
        self.server = HTTPServer(('0.0.0.0', 8090), CORSHandler)
        print("HTTP server starting on port 8090...")
        
        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("HTTP server interrupted")
        except Exception as e:
            print(f"HTTP server error: {e}")
    
    def show_status(self):
        """Show current streaming status"""
        while self.running:
            time.sleep(60)  # Update every minute
            if self.episode_history:
                recent = self.episode_history[-5:] if len(self.episode_history) >= 5 else self.episode_history
                print(f"STATUS: Played {len(self.episode_history)} episodes. Recent: {', '.join(recent)}")
    
    def run(self):
        """Main run method"""
        print("Dynamic Bob Ross HLS Streamer Starting...")
        print(f"Media directory: {self.media_dir}")
        print(f"HLS output directory: {self.hls_dir}")
        
        # Find and validate files
        if not self.find_and_validate_files():
            print("No valid video files found - exiting")
            return
        
        # Create HLS directory
        os.makedirs(self.hls_dir, exist_ok=True)
        
        # Start status monitoring
        threading.Thread(target=self.show_status, daemon=True).start()
        
        # Start streaming loop in background
        streaming_thread = threading.Thread(target=self.continuous_streaming_loop, daemon=True)
        streaming_thread.start()
        
        # Give streaming a moment to start
        time.sleep(10)
        
        print("="*60)
        print("DYNAMIC STREAM READY!")
        print(f"Access your stream at: http://YOUR_IP:8090/stream.m3u8")
        print("Each episode will play completely, then move to next random episode")
        print("="*60)
        
        # Start HTTP server (this will block)
        self.start_http_server()

if __name__ == "__main__":
    manager = DynamicStreamManager()
    manager.run()