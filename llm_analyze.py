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


MAX_TRANSCRIPT_CHARS = 60000  # ~15K tokens; enough for a full hour of CNBC


def send_to_llama(transcript_text, keep_thinking=False):
    """Send transcript to local llama.cpp server and return the response."""
    # Truncate to avoid slow prefill on very large transcripts (57KB+ seen in practice)
    if len(transcript_text) > MAX_TRANSCRIPT_CHARS:
        print(f"Transcript truncated from {len(transcript_text)} to {MAX_TRANSCRIPT_CHARS} chars for LLM prefill speed")
        transcript_text = transcript_text[:MAX_TRANSCRIPT_CHARS]

    # /no_think in the user message is the most reliable way to suppress Qwen3 thinking
    # at the chat-template level, regardless of llama.cpp version.
    user_content = f"/no_think\n\n{transcript_text}"

    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": user_content},
    ]

    payload = {
        "messages": messages,
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 8192,
        # Belt-and-suspenders: also disable via API field and chat_template_kwargs
        "thinking": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }

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
