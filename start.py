#!/usr/bin/env python3
"""Open CNBC live audio, intercept the stream URL, and record 60 minutes of audio to a dated MP3."""

import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://www.cnbc.com/live-audio/"
RECORDINGS_DIR = Path("/home/openclaw/.openclaw/skills/capture_stream_cnbc_audio/recordings")
DURATION_SECONDS = 60 * 60
BITRATE = "128k"

AUDIO_CONTENT_TYPES = ("audio/", "application/vnd.apple.mpegurl", "application/x-mpegurl")
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


def capture_stream_url() -> tuple[str | None, dict]:
    """Launch Chromium, navigate to CNBC, and capture the live stream URL."""
    captured_url = None
    captured_headers: dict = {}

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
            # Catch both .m3u8 (HLS) and .mp3 (direct stream) URLs from TuneIn/CDN
            is_stream = (".m3u8" in url or ".mp3" in url) and not any(skip in url for skip in SKIP_URL_FRAGMENTS)
            if is_stream:
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

        _dismiss_dialog(page)
        page.wait_for_timeout(1000)

        _click_play(page)
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

    return captured_url, captured_headers


def _dismiss_dialog(page):
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


def _click_play(page):
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


def start_recording(stream_url: str, out: Path, duration: int) -> subprocess.Popen:
    cmd = [
        "ffmpeg", "-y", "-i", stream_url,
        "-t", str(duration),
        "-f", "mp3",
        "-acodec", "libmp3lame",
        "-ab", BITRATE,
        "-ar", "44100",
        "-ac", "2",
        str(out),
    ]
    print(f"  ffmpeg: recording up to {duration}s → {out.name}")
    # stdout/stderr discarded to avoid the pipe-buffer deadlock:
    # proc.wait() would block forever if the pipe fills while ffmpeg runs 60 min.
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def concat_segments(segments: list[Path], final: Path) -> None:
    """Merge one or more MP3 segment files into final output, then clean up."""
    if len(segments) == 1:
        shutil.move(str(segments[0]), str(final))
        return

    concat_list = final.with_suffix(".concat.txt")
    with open(concat_list, "w") as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c", "copy", str(final)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True,
    )
    for seg in segments:
        seg.unlink(missing_ok=True)
    concat_list.unlink(missing_ok=True)


def main():
    out = output_path()
    tmp_base = out.with_name(out.name + ".tmp")
    print(f"Output file : {out}")
    print(f"Duration    : {DURATION_SECONDS // 60} minutes")
    print()

    deadline = time.monotonic() + DURATION_SECONDS
    segments: list[Path] = []
    attempt = 0

    try:
        while True:
            remaining = int(deadline - time.monotonic())
            if remaining < 30:
                print("Deadline reached.")
                break

            attempt += 1
            seg_path = tmp_base if attempt == 1 else tmp_base.with_suffix(f".seg{attempt}.tmp")

            print(f"\n--- Attempt {attempt} ({remaining}s remaining) ---")
            captured_url, _ = capture_stream_url()

            if not captured_url:
                print("ERROR: Could not intercept audio stream URL.", file=sys.stderr)
                if attempt == 1:
                    sys.exit(1)
                print("Stopping — could not re-capture stream URL.")
                break

            print(f"Stream URL  : {captured_url[:100]}...")
            proc = start_recording(captured_url, seg_path, remaining)
            proc.wait()
            print(f"ffmpeg exit : {proc.returncode}")

            if seg_path.exists() and seg_path.stat().st_size > 0:
                size_mb = seg_path.stat().st_size / 1_048_576
                segments.append(seg_path)
                print(f"Segment {attempt}: {size_mb:.1f} MB")
            else:
                print(f"WARNING: segment {attempt} empty or missing")

            remaining = int(deadline - time.monotonic())
            if remaining < 30:
                print("Deadline reached after segment.")
                break

            print(f"Stream closed early ({remaining}s left) — reconnecting in 5s...")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nStopped early by user.")
        try:
            proc.terminate()
            proc.wait()
        except Exception:
            pass
        if seg_path.exists() and seg_path.stat().st_size > 0 and seg_path not in segments:
            segments.append(seg_path)

    if not segments:
        print("ERROR: No audio was captured.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFinalizing {len(segments)} segment(s) → {out.name}")
    try:
        concat_segments(segments, out)
        print(f"Saved: {out}")
    except Exception as e:
        print(f"ERROR during concat: {e}", file=sys.stderr)
        if segments[0].exists():
            shutil.move(str(segments[0]), str(out))
            print(f"Saved (segment 1 only, concat failed): {out}")
        sys.exit(1)


if __name__ == "__main__":
    main()
