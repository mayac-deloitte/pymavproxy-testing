import os
import subprocess
import sys

def check_ffmpeg_installed():
    """Check if FFmpeg is installed."""
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print("FFmpeg is installed.")
    except subprocess.CalledProcessError:
        print("FFmpeg is not installed. Please install FFmpeg via Homebrew: brew install ffmpeg")
        sys.exit(1)

def stream_live_video(input_source, rtsp_port="8554", remote_ip="localhost", klv_metadata=None):
    """Stream live video (e.g., from a camera) with optional KLV metadata over RTSP."""
    rtsp_url = f"rtsp://{remote_ip}:{rtsp_port}/livestream"
    
    if klv_metadata:
        ffmpeg_command = [
            "ffmpeg",
            "-f", "avfoundation",  # On macOS, use AVFoundation for camera input; change accordingly for your platform
            "-i", input_source,    # Input source (e.g., "0" for default camera on macOS)
            "-i", klv_metadata,    # Input KLV metadata file
            "-map", "0:v",         # Map the video from the input source
            "-map", "1",           # Map the KLV metadata
            "-c:v", "copy",        # Copy video stream without re-encoding
            "-c:klv", "klv",       # Embed the KLV metadata
            "-f", "rtsp",          # Output format as RTSP
            rtsp_url               # RTSP stream URL
        ]
    else:
        ffmpeg_command = [
            "ffmpeg",
            "-f", "avfoundation",  # On macOS; for Linux use "v4l2", for Windows use "dshow"
            "-i", input_source,    # Input source (e.g., camera feed)
            "-c:v", "copy",        # Copy video stream without re-encoding
            "-f", "rtsp",          # Output format as RTSP
            rtsp_url               # RTSP stream URL
        ]

    print(f"Starting live RTSP stream at {rtsp_url} from source: {input_source}...")
    try:
        subprocess.run(ffmpeg_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during live streaming: {e}")
        sys.exit(1)

def main():
    # Replace these with your actual live input source and optional KLV metadata path
    input_source = "0"  # For macOS: "0" is the default camera; on Linux use "/dev/video0". Windows: Use "-f dshow -i video=" and specify the device name for the camera.
    klv_metadata = None  # Path to your KLV metadata file, or set to None if no KLV is needed

    # Set the RTSP server details
    rtsp_port = "8554"  # Default RTSP port
    remote_ip = "localhost"  # Use 'localhost' for local streaming or replace with your machine's IP address

    # Check if FFmpeg is installed
    check_ffmpeg_installed()

    # Stream the live video with or without KLV metadata over RTSP
    stream_live_video(input_source, rtsp_port, remote_ip, klv_metadata)

if __name__ == "__main__":
    main()
