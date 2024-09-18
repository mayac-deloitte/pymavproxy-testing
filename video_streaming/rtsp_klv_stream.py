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

def check_for_klv(input_video):
    """Check if the input video already has KLV metadata embedded."""
    ffprobe_command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "d",
        "-show_entries", "stream_tags=codec_name",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_video
    ]
    try:
        result = subprocess.run(ffprobe_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # If output contains "klv", the video has KLV metadata
        return "klv" in result.stdout.decode().strip()
    except subprocess.CalledProcessError:
        print(f"Error checking for KLV in {input_video}. Proceeding without checking.")
        return False

def embed_klv_metadata(input_video, klv_metadata, output_video):
    """Embed KLV metadata into a video using FFmpeg, if KLV metadata is provided."""
    if klv_metadata:
        ffmpeg_command = [
            "ffmpeg",
            "-i", input_video,
            "-i", klv_metadata,
            "-map", "0:v",
            "-map", "1",
            "-c:v", "copy",
            "-c:klv", "klv",
            output_video
        ]
        
        print(f"Embedding KLV metadata from {klv_metadata} into {input_video}...")
        try:
            subprocess.run(ffmpeg_command, check=True)
            print(f"Successfully created video with KLV metadata: {output_video}")
        except subprocess.CalledProcessError as e:
            print(f"Error during KLV metadata embedding: {e}")
            sys.exit(1)
    else:
        # If no KLV metadata is provided, just copy the input video to the output without changes
        ffmpeg_command = [
            "ffmpeg",
            "-i", input_video,
            "-c:v", "copy",
            output_video
        ]
        
        print(f"No KLV metadata provided. Copying {input_video} to {output_video}...")
        try:
            subprocess.run(ffmpeg_command, check=True)
            print(f"Successfully copied video to {output_video}")
        except subprocess.CalledProcessError as e:
            print(f"Error during video copying: {e}")
            sys.exit(1)

def stream_klv_video(output_video, remote_ip = "localhost", rtsp_port="8554"):
    """Stream the video with or without KLV metadata using FFmpeg's internal RTSP server."""
    rtsp_url = f"rtsp://{remote_ip}:{rtsp_port}/klvstream"  # Using localhost for RTSP binding
    
    # Command to stream video without audio
    ffmpeg_command = [
        "ffmpeg",
        "-re",
        "-i", output_video,
        "-an",  # Disable audio stream
        "-c:v", "copy",  # Copy video stream without re-encoding
        "-f", "rtsp",    # Set the format to RTSP
        rtsp_url         # Output to the local RTSP server URL
    ]
    
    print(f"Starting internal RTSP server and streaming at {rtsp_url}...")
    try:
        subprocess.run(ffmpeg_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during RTSP streaming: {e}")
        sys.exit(1)

def main():
    # Replace these with your actual video and metadata file paths
    input_video = "/Users/mcohen7/Library/CloudStorage/OneDrive-Deloitte(O365D)/Documents/Defence/pymavproxy-testing/video_streaming/sample.mp4"  # Path to your source video file
    klv_metadata = None  # Path to your KLV metadata file, or set to None if no KLV is needed
    output_video_with_klv = "output_video_with_klv.mkv"  # Output file with embedded KLV metadata (or just video copy)

    # Set the RTSP server details
    rtsp_port = "8554"  # Default RTSP port
    remote_ip = "locahost"

    # Check if FFmpeg is installed
    check_ffmpeg_installed()

    # Check if input video already has KLV metadata embedded
    if check_for_klv(input_video):
        print(f"The video {input_video} already contains KLV metadata.")
        # Skip embedding step and proceed to streaming
        output_video_with_klv = input_video  # No need to modify the video
    else:
        # Embed KLV metadata into the video (if it's provided)
        embed_klv_metadata(input_video, klv_metadata, output_video_with_klv)

    # Stream the video with or without KLV metadata using FFmpeg's internal RTSP server
    stream_klv_video(output_video_with_klv, remote_ip, rtsp_port)

if __name__ == "__main__":
    main()