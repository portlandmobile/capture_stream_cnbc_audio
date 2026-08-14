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

A cron job fires at **6:00 AM PST Monday–Friday**. It runs the entire pipeline: record → transcribe → analyze → deliver.

---

## Pipeline

```
Step 1: Start recorder (start.py, background) → polls until ~60 min recording finishes
Step 2: Transcribe with Whisper-ctranslate2 (CPU, ~5-10 min)
Step 3: LLM analysis with llm_analyze.py (~5 min)
Step 4: Format with format_report.py + save + Telegram (~2 min)
Total: ~70 minutes
```

---

## Step 1 — Start the Recorder

```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
.venv/bin/python3 start.py
```

**IMPORTANT:** Run this with `background: true`, `yieldMs: 10000`, and `timeout: 3600`.

Then poll using `process(action="poll", sessionId=<session-name>, timeout=600000)` every ~2-3 minutes until the MP3 output file appears in `recordings/`. Use `ls -la recordings/*.mp3*` to check periodically.

The recording is done when the `.tmp` file disappears and the final `.mp3` exists with a stable size (~50-60 MB).

> **Note:** The recorder uses Playwright (Chromium). Ensure the machine is running and network-accessible when the cron fires. The browser runs with `headless=False` in the script — if headless mode is needed for your environment, change the launch args accordingly.

---

## Step 2 — Transcribe with Whisper-ctranslate2

**Wait 30 seconds** after the recording finishes (ffmpeg may still be closing the file). Check that the `.mp3` exists and has a stable size before starting.

```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
whisper-ctranslate2 recordings/YYYY-MM-DD.mp3 \
  --model medium \
  --language en \
  --output_format txt \
  --output_dir recordings/ \
  --device cpu \
  --compute_type int8
```

**IMPORTANT — Do NOT include `sleep 30` in the exec command.** Instead, do a `ls -la recordings/YYYY-MM-DD.mp3` first, wait 30 seconds in your turn (or use `process` to poll), then fire the whisper command.

**CRITICAL EXECUTION RULES:**

1. **ALWAYS use `background: true`** — never fire whisper synchronously. Long-running processes will be killed if the agent's turn ends mid-execution.
2. Set `timeout: 900` (15 min) and `yieldMs: 15000` on the exec call.
3. After starting, **poll with `process(action="poll", sessionId=<name>, timeout=600000)`** until the process exits.
4. When polling returns `exitCode` is non-`None` or says `Process exited`, verify the output file:
   ```bash
   ls -la recordings/YYYY-MM-DD.txt && wc -l recordings/YYYY-MM-DD.txt
   ```
5. **Do NOT re-run whisper unless you see a real failure** (exit code, explicit error, or the file genuinely doesn't exist after the process exited). Each re-run overwrites the output file and wastes time.
6. If the transcript file already exists with 800+ lines, the job is done — move on to Step 3.

Replace `YYYY-MM-DD` with today's date. The transcript will be saved as `recordings/YYYY-MM-DD.txt`.

> Whisper is installed system-wide at `/home/openclaw/.local/bin/whisper-ctranslate2`.

> **IMPORTANT:** After Step 2 completes, verify the file exists with `ls -la recordings/YYYY-MM-DD.txt` and line count. **Do NOT read or display the transcript content** — it is 40–60KB and loading it into your context will slow the entire session significantly.

---

## Step 3 — LLM Analysis

```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
.venv/bin/python3 llm_analyze.py 'recordings/YYYY-MM-DD.txt' --output 'analysis/YYYY-MM-DD-analysis.md'
```

**Do NOT use `--keep-thinking`** — it causes the model to output reasoning text instead of the required JSON, breaking downstream parsing. The model will produce clean JSON output without thinking mode.

**IMPORTANT:** Run this with `background: true`, `yieldMs: 30000`, and `timeout: 900`.

Then poll with `process(action="poll", sessionId=<name>, timeout=600000)` until it exits. After completion, verify with `ls -la analysis/YYYY-MM-DD-analysis.md` only.

> **IMPORTANT:** Do NOT read the transcript file before or after this step — `llm_analyze.py` handles all file I/O internally.

---

## Step 4 — Format & Deliver

**CRITICAL: Do NOT re-run the local LLM on the analysis file.** The analysis from Step 3 is already structured JSON. Use the formatting script — no additional LLM calls needed.

### 4a. Run the formatting script

```bash
cd /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio
.venv/bin/python3 format_report.py YYYY-MM-DD --output YYYY-MM-DD-report.md
```

This reads `analysis/YYYY-MM-DD-analysis.md`, parses the JSON, groups by sentiment (BULLISH/BEARISH/NEUTRAL), and writes a clean markdown report to `YYYY-MM-DD-report.md`.

The output format:
```
CNBC Morning Audio — YYYY-MM-DD
================================

**BULLISH**

- **$TICKER** (Company) — tag1, tag2
  One-line summary

**BEARISH**

- **$TICKER** (Company) — tag1, tag2
  One-line summary

**NEUTRAL / ANALYST FOCUS**

- **$TICKER** (Company) — tag1, tag2
  One-line summary

---

**Key Themes:** Bullish/Bearish/Mixed sentiment. Top mentions: $T1, $T2, $T3.
```

### 4b. Save & Deliver

1. Read the generated report from `YYYY-MM-DD-report.md`
2. Save it to `/home/openclaw/MyVault/Projects/Trading/CNBC_Analysis/YYYY-MM-DD.md`
3. Send it to the **R-P Investment Group** via Telegram:
   - **channel:** `telegram`
   - **target:** `-1003675085814`
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
├── format_report.py      ← format JSON analysis into Telegram report
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
- `whisper-ctranslate2` — speech-to-text transcription (`/home/openclaw/.local/bin/whisper-ctranslate2`)
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
| Whisper re-run kills transcript | Agent fired whisper without `background:true` | The skill now enforces background execution. Old runs may have orphaned whisper processes — check with `ps aux | grep whisper-ctranslate2` and kill any orphans before next run |
