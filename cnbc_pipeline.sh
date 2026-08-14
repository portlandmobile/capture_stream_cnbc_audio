#!/bin/bash
# CNBC Morning Audio Capture Pipeline
# Wraps: start.py → whisper-ctranslate2 → llm_analyze.py → format_report.py
# Delivery is handled separately by the OpenClaw agent (Telegram bot token not available here).
#
# Usage: cnbc_pipeline.sh
#   Runs all 4 pipeline steps. Writes report to YYYY-MM-DD-report.md.
#
# Designed to be called by OpenClaw cron as a single background exec:
#   exec(command="bash /home/openclaw/.openclaw/skills/capture_stream_cnbc_audio/cnbc_pipeline.sh", background:true, timeout:7200)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DATE=$(date +%Y-%m-%d)
VAULT_DIR="/home/openclaw/MyVault/Projects/Trading/CNBC_Analysis"
TELEGRAM_CHAT="-1003675085814"
TELEGRAM_BOT_TOKEN="${CNBC_TELEGRAM_BOT_TOKEN:-}"



log() {
  echo "[$(date '+%H:%M:%S')] $*"
}

# ============================================================
# Step 1: Record (via start.py)
# ============================================================
log "Step 1: Recording CNBC audio..."
.venv/bin/python3 start.py &
REC_PID=$!

# Poll until MP3 appears and stabilizes
POLL_INTERVAL=60
LAST_SIZE=0
STABLE_COUNT=0

while kill -0 $REC_PID 2>/dev/null; do
  mp3=$(ls -1 recordings/*.mp3 2>/dev/null | grep -v tmp | head -1 || true)
  if [[ -n "$mp3" ]]; then
    SIZE=$(stat -c %s "$mp3" 2>/dev/null || echo 0)
    if [[ "$SIZE" -gt 0 && "$SIZE" -eq "$LAST_SIZE" ]]; then
      STABLE_COUNT=$((STABLE_COUNT + 1))
      if [[ $STABLE_COUNT -ge 3 ]]; then
        log "  Recording stable at ${SIZE} bytes ($((SIZE/1048576)) MB)"
        break
      fi
    else
      STABLE_COUNT=0
      LAST_SIZE=$SIZE
    fi
  fi
  sleep $POLL_INTERVAL
done

wait $REC_PID 2>/dev/null || true

MP3=$(ls -1 recordings/*.mp3 2>/dev/null | grep -v tmp | head -1 || true)
if [[ -z "$MP3" ]]; then
  log "ERROR: No MP3 file found after recording."
  exit 1
fi

SIZE_MB=$(( $(stat -c %s "$MP3") / 1048576 ))
log "  Recording complete: ${MP3} ($SIZE_MB MB)"

# ============================================================
# Step 2: Transcribe (via whisper-ctranslate2)
# ============================================================
log "Step 2: Transcribing..."

# Wait for ffmpeg to finish writing
sleep 30

if [[ ! -f "recordings/${DATE}.txt" ]]; then
  whisper-ctranslate2 "recordings/${DATE}.mp3" \
    --model medium \
    --language en \
    --output_format txt \
    --output_dir recordings/ \
    --device cpu \
    --compute_type int8

  if [[ ! -f "recordings/${DATE}.txt" ]]; then
    log "ERROR: Transcription produced no output file."
    exit 1
  fi
fi

LINES=$(wc -l < "recordings/${DATE}.txt")
KB=$(du -k "recordings/${DATE}.txt" | cut -f1)
log "  Transcription complete: ${LINES} lines, ${KB} KB"

# ============================================================
# Step 3: Analyze (via llm_analyze.py)
# ============================================================
log "Step 3: Running LLM analysis..."

.venv/bin/python3 llm_analyze.py "recordings/${DATE}.txt" \
  --output "analysis/${DATE}-analysis.md"

if [[ ! -f "analysis/${DATE}-analysis.md" ]]; then
  log "ERROR: Analysis produced no output file."
  exit 1
fi

KB=$(du -k "analysis/${DATE}-analysis.md" | cut -f1)
log "  Analysis complete: ${KB} KB"

# ============================================================
# Step 4: Format (via format_report.py)
# ============================================================
log "Step 4: Formatting report..."

.venv/bin/python3 format_report.py "$DATE" --output "${DATE}-report.md"

if [[ ! -f "${DATE}-report.md" ]]; then
  log "ERROR: Format produced no output file."
  exit 1
fi

KB=$(du -k "${DATE}-report.md" | cut -f1)
log "  Report formatted: ${KB} KB"

# Save to vault
mkdir -p "$VAULT_DIR"
cp "${DATE}-report.md" "${VAULT_DIR}/${DATE}.md"
log "  Saved to vault: ${VAULT_DIR}/${DATE}.md"

# ============================================================
# Step 5: Deliver to Telegram
# ============================================================
# Delivery is handled by the OpenClaw agent (has the Telegram bot credentials).
# The report file is ready at ${DATE}-report.md and has been saved to the vault.
# The agent should:
#   1. Read the report from YYYY-MM-DD-report.md (or the vault copy)
#   2. Send it to Telegram using the message tool
#   3. Include the "Test run" note for manual runs, remove for production cron

log "Report ready at: ${DATE}-report.md"
log "Vault copy: ${VAULT_DIR}/${DATE}.md"

log "=== Pipeline complete (delivery handled by OpenClaw agent) ==="
