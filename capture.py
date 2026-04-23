#!/usr/bin/env python3
"""Capture system audio output to a dated MP3 file."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

RECORDINGS_DIR = Path("/home/openclaw/.openclaw/skills/capture_stream_cnbc_audio/recordings")
DURATION_SECONDS = 60 * 60  # 60 minutes
BITRATE = "128k"


def get_default_monitor() -> str:
    result = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True)
    sink = result.stdout.strip()
    if not sink:
        print("ERROR: Could not detect default audio sink.", file=sys.stderr)
        sys.exit(1)
    return f"{sink}.monitor"


def main():
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    monitor = get_default_monitor()
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_file = RECORDINGS_DIR / f"{date_str}.mp3"

    # Append a counter if a file for today already exists
    if output_file.exists():
        counter = 2
        while (RECORDINGS_DIR / f"{date_str}-{counter}.mp3").exists():
            counter += 1
        output_file = RECORDINGS_DIR / f"{date_str}-{counter}.mp3"

    print(f"Monitor source : {monitor}")
    print(f"Output file    : {output_file}")
    print(f"Duration       : {DURATION_SECONDS // 60} minutes")
    print("Recording — press Ctrl+C to stop early.\n")

    cmd = [
        "ffmpeg",
        "-f", "pulse",
        "-i", monitor,
        "-t", str(DURATION_SECONDS),
        "-acodec", "libmp3lame",
        "-ab", BITRATE,
        "-ar", "44100",
        "-ac", "2",
        str(output_file),
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"\nSaved: {output_file}")
    except KeyboardInterrupt:
        print(f"\nStopped early. Partial file saved: {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg exited with error {e.returncode}.", file=sys.stderr)
        sys.exit(e.returncode)


if __name__ == "__main__":
    main()
