---
name: capture-stream-cnbc-audio
description: Capture and analysis the CNBC stock podcast with Jim Crammer
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: [".venv/bin/python3"]
---
# Capture CNBC Live Audio & Extract Stock Mentions

## Purpose

Records one hour of CNBC live audio each weekday morning, transcribes it, and extracts every stock ticker and company mentioned along with the surrounding sentiment context.

---

## Trigger

Two cron jobs fire each weekday:

- **Step 0** (6:00 AM Mon–Fri): Starts the recorder and **immediately exits**. Does NOT transcribe, analyze, or deliver.
- **Step 1–3** (7:10 AM Mon–Fri): Transcribes, analyzes, and delivers results.

> ⚠️ **NEVER read this SKILL.md from a cron job.** The cron payloads have the steps hardcoded. Re-reading this file causes the agent to hallucinate and run steps out of order (e.g., Step 0 running Steps 1–3 too).

## 🔒 Critical Rule: Two-Cron Isolation

This skill uses a **two-cron architecture** to avoid a 60-minute blocking session:

```
Cron A (6:00 AM) ──► Start recorder (background) ──► EXIT immediately
Cron B (7:10 AM) ──► Transcribe → Analyze → Deliver
```

**When invoked as Step 0 (6:00 AM):**
- Start the recorder and exit. That is the ENTIRE job.
- Do NOT run Whisper.
- Do NOT run `llm_analyze.py`.
- Do NOT send Telegram messages.
- Do NOT save vault files.
- Do NOT read this SKILL.md.

**When invoked as Step 1–3 (7:10 AM):**
- Check if `recordings/YYYY-MM-DD.txt` exists and is non-empty.
- If yes → skip Whisper (someone already transcribed), go straight to analysis.
- If no → run Whisper, then analysis, then deliver.
- Do NOT re-read this SKILL.md.

Violating this separation causes **duplicate transcriptions**, **duplicate reports**, and **hour-long CPU waste**. The transcript file (`recordings/YYYY-MM-DD.txt`) is the lock mechanism — if it exists, transcription is done.

---

## Agent Architecture

Two isolated cron jobs coordinate the pipeline:

```
Cron A (6:00 AM)                    Cron B (7:10 AM)
┌──────────────────────────┐        ┌─────────────────────────────┐
│ 1. cd to skill dir       │        │ 1. Check recordings/        │
│ 2. start.py (background) │        │    YYYY-MM-DD.txt exists?   │
│ 3. EXIT                  │        │    Yes → skip to Step 2     │
└──────────────────────────┘        │    No  → run Whisper        │
             │                      └──────────┬──────────────────┘
             ▼                                 ▼
      60 min recording                      2. llm_analyze.py
      recordings/YYYY-MM-DD.mp3             3. Format summary
                                             4. Save to vault
                                             5. Send to Telegram
```

---

## Step 0 — Start the Recorder

**Invoke: Cron A at 6:00 AM Mon–Fri**

When this cron triggers, run EXACTLY these commands and then STOP:

```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
.venv/bin/python3 start.py
```

Run with `background: true` and `yieldMs: 10000` so it returns immediately.

**Then report the PID and exit.** That is your entire job. The recorder continues in the background for 60 minutes.

> **Note:** The recorder uses Playwright (Chromium). Ensure the machine is running and network-accessible when the cron fires. The browser runs with `headless=False` in the script — if headless mode is needed for your environment, change the launch args accordingly.

> **DO NOT proceed to Steps 1–3.** They are handled by the separate 7:10 AM cron.

> **DO NOT re-read this SKILL.md.** The cron payload already specifies what to do.

---

## Step 1 — Transcribe with Whisper-ctranslate2

**Invoke: Cron B at 7:10 AM Mon–Fri**

**FIRST, check the transcript lock:**
```bash
ls -la /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio/recordings/$(date +%Y-%m-%d).txt
```

- If the file exists and is **non-empty** → Whisper already ran. **Skip to Step 2.**
- If the file does **not exist** or is **empty** → run Whisper:

```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
sleep 30
whisper-ctranslate2 recordings/YYYY-MM-DD.mp3 \
  --model medium \
  --language en \
  --output_format txt \
  --output_dir analysis/ \
  --device cpu \
  --compute_type int8
```

Replace `YYYY-MM-DD` with today's date. The transcript will be saved as `recordings/YYYY-MM-DD.md`.  Replace the file extension from .txt to .md if needed.

> Whisper is installed system-wide at `/home/openclaw/.local/bin/whisper-ctranslate2`.

---

## Step 2 — Parse the Transcript for Stock Mentions

```bash
.venv/bin/python3 llm_analyze.py 'recordings/YYYY-MM-DD.txt' --keep-thinking --output 'analysis/YYYY-MM-DD-analysis.md'
```

---

## Step 3 — Present the Results

Read the parsed analysis from `'analysis/YYYY-MM-DD-analysis.md'` and output a clean, categorized summary.

**Group stocks by sentiment** (bullish, bearish, neutral/analyst). For each stock, show:
- Bold ticker with company name in parentheses
- Sentiment label + context tags (earnings, analyst, news, M&A, etc.)
- One representative quote in a blockquote

Then add a **key themes** section at the bottom — a short paragraph of the biggest narratives, not just a dry count.

**Example output format:**

```
CNBC Morning Audio — 2026-04-29
================================

**BULLISH**

- **$V** (Visa) — earnings, 17% rev gain, 20% EPS beat
- **$STX** (Seagate) — earnings, data center demand
- **$GLW** (Corning) — earnings, data center/fiber play
- **$BE** (Bloom Energy) — news, clean energy
- **$NXPI** (NXP Semi) — earnings, auto sector strength
- **$ETSY** (Etsy) — earnings, consumer resilience
- **$TMUS** (T-Mobile) — earnings, +217K wireless additions
- **$SBUX** (Starbucks) — analyst, raised full-year outlook, beat streak

**BEARISH**

- **$GEHC** (GE Healthcare) — earnings miss
- **$HOOD** (Robinhood) — EPS miss, crypto drag
- **$BF.B** (Brown Forman) — M&A fallout (Pernod Ricard walked away)

**NEUTRAL / ANALYST FOCUS**

- **$AAPL** (Apple) — earnings signal to watch
- **$AMZN / $GOOG / $META** (Amazon, Alphabet, Meta) — MAG-7 earnings tonight
- **$CHTR / $CMCSA / $T** (Charter, Comcast, AT&T) — fixed wireless competition
- **$PSUS** (Pershing Square USA) — Bill Ackman IPO
```

No blockquotes. One-line concise summaries next to each ticker. Keep it tight.

**Rules:**
- If a ticker is mentioned multiple times with different contexts, merge into one entry with the most representative quote
- Use `**` for bold ticker headers, `>` for quotes, `---` separator before SUMMARY
- Keep it readable — no markdown tables
- Always end with a key themes paragraph (1-2 sentences) that captures the day's narrative

**Save & Deliver:**
1. Save the summary to `/home/openclaw/MyVault/Projects/Trading/CNBC_Analysis/YYYY-MM-DD.md`
2. Send it to the **Daily Briefing channel** via Telegram:
   - **channel:** `telegram`
   - **target:** `-1003815784979`
   - Use the `message` tool with `action=send`
- Include a note at the bottom for testing runs: `*(Test run — format & flow verified ✅)*`, but remove it for production cron deliveries.

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
| Duplicate Whisper processes running | Step 0 cron ran Steps 1–3, then Step 1–3 cron also transcribed | Check if `recordings/YYYY-MM-DD.txt` exists before starting transcription. Kill duplicate `whisper-ctranslate2` processes. Verify cron payloads match the latest SKILL.md. |
| Two identical reports delivered to Telegram | Step 0 cron completed full pipeline, then Step 1–3 cron also delivered | The transcript file lock (`recordings/YYYY-MM-DD.txt`) prevents re-transcription. If you see duplicates, the lock was bypassed — check the cron payloads and ensure they don't re-read SKILL.md. |
