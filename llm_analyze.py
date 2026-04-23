#!/usr/bin/env python3
"""
Analyze a CNBC transcript for stock mentions using local llama.cpp server.
Mirrors the web UI prompt and sampling parameters for rich, detailed output.
"""
import re
import sys
import os
import argparse
import requests
from datetime import date

PROMPT_TEMPLATE = """\
Attached is the transcript of a stock & ecomonic analysis podcast.
Read the transcript and extract:

- **Ticker symbols** — E.g. any word matching `$AAPL`, `AAPL`, or spoken as "Apple stock", "shares of Apple", etc.
- **Company names** and their corresponding tickers
- **Context around each mention** — classify each as one or more of:
  - `bullish` — positive outlook, buy recommendation, price target raised, beat earnings
  - `bearish` — negative outlook, sell recommendation, price target cut, missed earnings
  - `earnings` — quarterly results discussed
  - `M&A` — merger, acquisition, or takeover mentioned
  - `analyst` — analyst rating or price target change
  - `news` — general news item with no clear directional sentiment
- **Economic News** 
  - `macro` — mentioned in context of broad market/economic discussion

The transcript contains advertisement. Do not output companies or info related to the ad mention.  Otherwise, capture the verbatim sentence(s) around each mention as a short quote for reference.

---

{transcript}"""


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> blocks emitted by reasoning models."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def main():
    parser = argparse.ArgumentParser(
        description="Extract stock mentions from a CNBC transcript via local llama.cpp."
    )
    parser.add_argument("file_path", help="Path to the transcript .txt file")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8080/v1/chat/completions",
        help="llama.cpp server endpoint (default: http://127.0.0.1:8080/v1/chat/completions)",
    )
    parser.add_argument(
        "--temperature", type=float, default=1.0,
        help="Sampling temperature — web UI default is 1.0 (default: 1.0)",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=8192,
        help="Max tokens to generate (default: 8192)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file path (default: report_YYYY-MM-DD.md beside the transcript)",
    )
    parser.add_argument(
        "--keep-thinking", action="store_true",
        help="Keep <think> blocks in output instead of stripping them",
    )
    args = parser.parse_args()

    if not os.path.exists(args.file_path):
        print(f"Error: file not found: {args.file_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.file_path, encoding="utf-8") as f:
        transcript = f.read()

    prompt = PROMPT_TEMPLATE.format(transcript=transcript)

    # Sampling parameters that match the llama.cpp web UI defaults.
    # Key differences vs the old scripts:
    #   - /v1/chat/completions applies the model's chat template (not raw /completion)
    #   - no stop tokens — let the model finish naturally
    #   - no JSON coercion — natural markdown output
    #   - temperature 1.0 / top_p 0.95 / min_p 0.05 match web UI defaults
    payload = {
        "model": "local",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": args.temperature,
        "top_p": 0.95,
        "top_k": 40,
        "min_p": 0.05,
        "repeat_penalty": 1.1,
        "n_predict": args.max_tokens,
        "cache_prompt": True,
        "reasoning_format": "auto",
        "stream": False,
    }

    print(f"Sending {len(transcript):,} chars to {args.url}")
    print(f"temperature={args.temperature}  top_p=0.95  top_k=40  min_p=0.05  max_tokens={args.max_tokens}")

    try:
        resp = requests.post(args.url, json=payload, timeout=600)
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        print(f"Cannot connect to llama.cpp at {args.url}", file=sys.stderr)
        print("Is the server running?  llama-server -m model.gguf --port 8080", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("Request timed out after 10 min. Try a shorter transcript.", file=sys.stderr)
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        print(resp.text[:500], file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    message = data["choices"][0]["message"]
    content = message.get("content", "")
    reasoning = message.get("reasoning_content", "")

    if not args.keep_thinking:
        content = strip_thinking(content)

    # Default output path: same directory as the transcript, named by today's date
    if args.output:
        output_path = args.output
    else:
        transcript_dir = os.path.dirname(os.path.abspath(args.file_path))
        output_path = os.path.join(transcript_dir, f"report_{date.today()}.md")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\n✅  Saved to: {output_path}")
    print(f"    Response: {len(content):,} chars", end="")
    if reasoning:
        print(f"   |  Thinking (stripped): {len(reasoning):,} chars", end="")
    print()
    print("\n" + "─" * 70)
    preview = content[:3000]
    print(preview)
    if len(content) > 3000:
        print(f"\n… ({len(content) - 3000:,} more chars — see {output_path})")


if __name__ == "__main__":
    main()
