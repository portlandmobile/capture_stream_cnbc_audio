#!/usr/bin/env python3
"""Analyze a CNBC transcript via the local llama.cpp server.

Usage:
    python llm_analyze.py <transcript_path> [--keep-thinking] [--output <path>]
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

LLAMA_URL = "http://localhost:8080/v1/chat/completions"

PROMPT = """You are a financial sentiment analyst. Analyze this CNBC audio transcript and extract every stock ticker and company mentioned.

For each mention, provide:
1. The ticker symbol (if identifiable) and company name
2. Sentiment: BULLISH, BEARISH, or NEUTRAL
3. Context tags: earnings, analyst_upgrade, analyst_downgrade, news, M&A, capex, guidance, insider_trading, macro, sector_rotation, etc.
4. A brief summary (one line)
5. A representative quote from the transcript

Format the output as a JSON array of objects with these fields:
- ticker: string (e.g., "NVDA", "TSLA", or null if no ticker)
- company: string (company name)
- sentiment: "BULLISH" | "BEARISH" | "NEUTRAL"
- tags: array of context tags
- summary: string (one-line summary)
- quote: string (representative quote from transcript)

Rules:
- Group multiple mentions of the same ticker/company into a single entry
- If a ticker is mentioned with mixed sentiment, use the predominant sentiment and note both in summary
- Include ALL tickers mentioned, even if briefly
- Be thorough — don't miss any tickers
- For companies without a clear ticker, use the company name as the identifier
- Return ONLY valid JSON. No markdown, no explanation, no additional text. Start with [ and end with ]."""


def send_to_llama(transcript_text, keep_thinking=False):
    """Send transcript to local llama.cpp server and return the response."""
    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": transcript_text},
    ]

##### These are included in the payload.  Leaving them here for reference
#        "model": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
#        "temperature": 0.1,
#        "max_tokens": 8192,
    payload = {
        "messages": messages,
        "stream": False,
        "model": "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf",
        "temperature": 0.5,
        "max_tokens": 10240,
    }

    # Note: thinking mode causes the model to output reasoning text but
    # not the actual JSON response. For structured output, disable thinking.
    # If keep_thinking is requested, use it but the output may be reasoning-only.
    if keep_thinking:
        # Disable thinking for reliable JSON output
        payload["thinking"] = False

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        LLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            message = result["choices"][0]["message"]
            # Prefer content; fall back to reasoning_content if thinking was used
            content = message.get("content", "")
            if not content:
                content = message.get("reasoning_content", "")
            return content
    except urllib.error.URLError as e:
        print(f"ERROR: Could not connect to llama server at {LLAMA_URL}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Analyze CNBC transcript with local LLM")
    parser.add_argument("transcript_path", help="Path to the transcript .txt file")
    parser.add_argument("--keep-thinking", action="store_true", help="Enable thinking mode")
    parser.add_argument("--output", help="Output analysis file path", default=None)
    args = parser.parse_args()

    # Read transcript
    with open(args.transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    print(f"Transcript loaded: {len(transcript)} chars, {len(transcript.splitlines())} lines")

    # Send to LLM
    print("Sending to local LLM for analysis...")
    result = send_to_llama(transcript, keep_thinking=args.keep_thinking)

    # Clean up the result (remove markdown code blocks if present)
    result = result.strip()
    if result.startswith("```json"):
        result = result[7:]
    if result.startswith("```"):
        result = result[3:]
    if result.endswith("```"):
        result = result[:-3]
    result = result.strip()

    # Write output
    output_path = args.output
    if not output_path:
        # Derive from transcript path
        import os
        base = os.path.splitext(args.transcript_path)[0]
        output_path = base + "-analysis.md"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"Analysis saved to: {output_path}")
    print(f"Output size: {len(result)} chars")


if __name__ == "__main__":
    main()
