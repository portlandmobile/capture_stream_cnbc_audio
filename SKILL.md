---
name: capture-stream-cnbc-audio
description: Capture and analysis the CNBC stock podcast with Jim Crammer
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: [".venv/bin/python3", "qmd"]
---
# Capture CNBC Live Audio & Extract Stock Mentions

## Purpose

Records one hour of CNBC live audio each weekday morning, transcribes it, and extracts every stock ticker and company mentioned along with the surrounding sentiment context.

---

## Trigger

A cron job fires at **6:00 AM PST Monday–Friday** and invokes this skill on the main OpenClaw agent.

---

## Agent Architecture

This skill uses a **two-step pattern** to avoid blocking the main agent for 60 minutes:

```
Main Agent (OpenClaw)
  │
  ├─► Step 0: Spawn recorder in background (exec with background=true)
  │       └─ runs: .venv/bin/python3 start.py
  │       └─ records for 60 minutes
  │       └─ saves recordings/YYYY-MM-DD.mp3
  │       └─ returns immediately to main agent
  │
  └─► Waits for recorder to finish (cron/heartbeat notifies)
        └─ Step 1: Transcribe with Whisper
        └─ Step 2: Parse transcript
        └─ Step 3: Present results
```

---

## Step 0 — Start the Recorder

When this skill is triggered, the main agent starts the recorder as a background process:

```
exec: .venv/bin/python3 start.py
background: true
```

The recorder runs headless, opens CNBC's live audio stream, and captures 60 minutes of audio to `recordings/YYYY-MM-DD.mp3`. The command returns immediately; the recording continues in the background.

> **Note:** The recorder uses Playwright (Chromium). Ensure the machine is running and network-accessible when the cron fires. The browser runs with `headless=False` in the script — if headless mode is needed for your environment, change the launch args accordingly.

---

## Step 1 — Transcribe with Whisper

Confirm the MP3 path, then transcribe:

```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
whisper recordings/YYYY-MM-DD.mp3 \
    --model medium \
    --language en \
    --output_format txt \
    --output_dir recordings/
```

Replace `YYYY-MM-DD` with today's date. The transcript will be saved as `recordings/YYYY-MM-DD.txt`.

> Whisper is installed system-wide at `/home/openclaw/.local/bin/whisper`. If you want a larger model, install it with `.venv/bin/pip install openai-whisper` and use `.venv/bin/python3 -m whisper` instead.

---

## Step 2 — Parse the Transcript for Stock Mentions

```bash
.venv/bin/python3 llm_analyze.py 'recordings/YYYY-MM-DD.txt' --keep-thinking --output 'analysis/YYYY-MM-DD-analysis.md'
```

---

## Step 3 — Present the Results

Output a clean, deduplicated summary in this format from `'analysis/YYYY-MM-DD-analysis.md'`:

```
CNBC Morning Audio — YYYY-MM-DD
================================

STOCKS MENTIONED
----------------

$AAPL  (Apple) — bullish, analyst
  > "Dan Ives raised his price target on Apple to $275, calling it a top pick..."

$TSLA  (Tesla) — bearish, earnings
  > "Tesla missed on both the top and bottom line, shares are down pre-market..."

$NVDA  (Nvidia) — bullish, macro
  > "Nvidia continues to benefit from AI infrastructure spending..."

... (continue for all tickers)

SUMMARY
-------
Total stocks mentioned : N
Bullish mentions       : N
Bearish mentions       : N
Earnings discussed     : N
```

If a ticker is mentioned multiple times with different contexts, merge all contexts into one entry with the most representative quote.

The output of the summary will be saved as `/home/openclaw/MyVault/Projects/Trading/CNBC_Analysis/YYYY-MM-DD.txt`.

Then send the summary to the **Daily Briefing channel** on Telegram:
- **channel:** `telegram`
- **target:** `-1003815784979`

Use bold for ticker headers, blockquotes (`>`) for quotes, and a `---` separator before the SUMMARY section. Keep it readable — no markdown tables. Include a note at the bottom: `*(Test run — format & flow verified ✅)*` for testing, but remove that note in production cron runs. Use the `message` tool with `action=send`.

---

## File Layout

```
capture_stream_cnbc_audio/
├── SKILL.md              ← this file
├── start.py              ← recording script (run by background agent)
├── capture.py            ← audio-only capture helper
├── inspect_player.py     ← dev utility for inspecting the player
├── llm_analyze.py        ← transcript analysis (calls local llama.cpp)
├── recordings/
│   ├── YYYY-MM-DD.mp3    ← raw audio
│   └── YYYY-MM-DD.txt    ← Whisper transcript
├── analysis/
│   └── YYYY-MM-DD-analysis.md  ← LLM analysis output
└── .venv/                ← Python virtualenv (Playwright + Whisper)
```

---

## Dependencies

**System-wide:**
- `whisper` — speech-to-text transcription (`/home/openclaw/.local/bin/whisper`)
- `ffmpeg` — audio capture
- `pulseaudio` — audio routing (system package, must be running)

**Virtualenv (`.venv/`):**
- `playwright` — browser automation (Chromium)
- `openai-whisper` — optional, for larger model support

To reinstall the venv:
```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| No audio captured (silent MP3) | PulseAudio not running or wrong sink | Run `pactl get-default-sink` and confirm audio is routed there |
| TuneIn frame not found | CNBC page layout changed | Run `inspect_player.py` to re-examine the player DOM |
| Whisper runs out of memory | Model too large for available RAM | Switch `--model medium` → `--model small` or use `.venv/bin/python3 -m whisper` with a smaller model if you installed the venv version |
| Cron job never fires | DISPLAY not set for headless browser | Ensure `DISPLAY=:0` or a virtual framebuffer (Xvfb) is configured in the cron environment |
| Background agent never reports back | start.py hung or crashed silently | Check `recordings/` for a partial MP3; kill any lingering ffmpeg/chromium processes |
