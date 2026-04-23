#!/usr/bin/env python3
"""Open CNBC live audio, intercept the stream URL, and record 60 minutes of audio to a dated MP3."""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.cnbc.com/live-audio/"
RECORDINGS_DIR = Path("/home/openclaw/.openclaw/skills/capture_stream_cnbc_audio/recordings")
DURATION_SECONDS = 60 * 60
BITRATE = "128k"

# Content-Type values that indicate a real audio stream or HLS playlist
AUDIO_CONTENT_TYPES = ("audio/", "application/vnd.apple.mpegurl", "application/x-mpegurl")

# Static/placeholder audio files that TuneIn loads before the real stream
SKIP_URL_FRAGMENTS = ("blank.mp3", "/resources/media/", "/resources/audio/")


def output_path() -> Path:
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = RECORDINGS_DIR / f"{date_str}.mp3"
    if path.exists():
        counter = 2
        while (RECORDINGS_DIR / f"{date_str}-{counter}.mp3").exists():
            counter += 1
        path = RECORDINGS_DIR / f"{date_str}-{counter}.mp3"
    return path


def temp_output_path(path: Path) -> Path:
    """Return a temp file path for ffmpeg to write to, avoiding "(deleted)" FD issues."""
    return path.with_name(path.name + ".tmp")


def finalize_output(tmp_path: Path, final_path: Path) -> None:
    """Atomic move from temp to final location."""
    print(f"  finalize: tmp={tmp_path} exists={tmp_path.exists()}")
    if tmp_path.exists():
        import shutil
        shutil.move(str(tmp_path), str(final_path))
    else:
        import shutil
        print(f"  ERROR: temp file missing, trying to move final directly...")
        if final_path.exists():
            print(f"  final exists too: {final_path.stat().st_size} bytes")


def start_recording(stream_url: str, headers: dict, out: Path) -> subprocess.Popen:
    cmd = ["ffmpeg", "-y"]
    if headers:
        header_str = "\r\n".join(f"{k}: {v}" for k, v in headers.items()) + "\r\n"
        cmd += ["-headers", header_str]
    cmd += [
        "-i", stream_url,
        "-t", str(DURATION_SECONDS),
        "-acodec", "libmp3lame",
        "-ab", BITRATE,
        "-ar", "44100",
        "-ac", "2",
        str(out),
    ]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def dismiss_dialog(page):
    for selector in [
        "button:has-text('Continue')",
        "button.save-preference-btn-handler",
        "button:has-text('Confirm My Choice')",
        "button:has-text('Accept All')",
        ".onetrust-accept-btn-handler",
        "#onetrust-accept-btn-handler",
    ]:
        try:
            page.click(selector, timeout=2000)
            print("  Dismissed consent dialog.")
            page.wait_for_timeout(1500)
            return
        except Exception:
            pass


def click_play(page):
    """Find the TuneIn iframe and click the visible play button."""
    tunein_frame = None
    for _ in range(20):
        for frame in page.frames:
            if "tunein" in frame.url:
                tunein_frame = frame
                break
        if tunein_frame:
            break
        page.wait_for_timeout(500)

    if not tunein_frame:
        print("ERROR: TuneIn player frame not found.", file=sys.stderr)
        sys.exit(1)

    print(f"  Found TuneIn player: {tunein_frame.url}")

    play_btn = tunein_frame.locator("div.play-button.loaded").last
    play_btn.wait_for(state="visible", timeout=10000)
    play_btn.click()
    print("  Clicked play button.")


def main():
    out = output_path()
    tmp_path = temp_output_path(out)
    print(f"Output file    : {out}")
    print(f"Duration       : {DURATION_SECONDS // 60} minutes")
    print()

    captured_url = None
    captured_headers = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--no-sandbox"],
        )
        page = browser.new_page()

        def handle_request(request):
            nonlocal captured_url, captured_headers
            if captured_url:
                return
            url = request.url
            if ".m3u8" in url and not any(skip in url for skip in SKIP_URL_FRAGMENTS):
                captured_url = url
                try:
                    captured_headers = {
                        k: v for k, v in request.headers.items()
                        if k.lower() in ("authorization", "cookie", "referer", "origin", "user-agent")
                    }
                except Exception:
                    pass
                print(f"  Captured stream (request): {url}")

        def handle_response(response):
            nonlocal captured_url, captured_headers
            if captured_url:
                return
            url = response.url
            if any(skip in url for skip in SKIP_URL_FRAGMENTS):
                print(f"  Skipping placeholder: {url}")
                return
            content_type = response.headers.get("content-type", "")
            if any(ct in content_type for ct in AUDIO_CONTENT_TYPES):
                captured_url = url
                try:
                    req_headers = response.request.headers
                    captured_headers = {
                        k: v for k, v in req_headers.items()
                        if k.lower() in ("authorization", "cookie", "referer", "origin", "user-agent")
                    }
                except Exception:
                    pass
                print(f"  Captured stream (response): {captured_url}  [{content_type}]")

        page.on("request", handle_request)
        page.on("response", handle_response)

        print(f"Opening {URL} ...")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        dismiss_dialog(page)
        page.wait_for_timeout(1000)

        click_play(page)

        # Give the player extra time to resolve the real stream after play is clicked
        page.wait_for_timeout(5000)

        print("  Waiting for stream URL...")
        for _ in range(40):
            if captured_url:
                break
            page.wait_for_timeout(500)

        try:
            browser.close()
        except Exception:
            pass

    if not captured_url:
        print("ERROR: Could not intercept audio stream URL.", file=sys.stderr)
        sys.exit(1)

    print(f"\nStream URL     : {captured_url}")
    print(f"Starting recording ...")
    proc = start_recording(captured_url, captured_headers, tmp_path)

    print(f"Recording for {DURATION_SECONDS // 60} minutes. Press Ctrl+C to stop early.\n")
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        print("\nStopped early.")

    # Atomically move temp file to final path
    finalize_output(tmp_path, out)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
