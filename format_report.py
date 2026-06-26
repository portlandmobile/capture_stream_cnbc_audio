#!/usr/bin/env python3
"""Format CNBC analysis JSON into a Telegram-ready markdown report.

Usage:
    python format_report.py <date> [--output <path>]

Reads analysis/YYYY-<date>-analysis.md, parses the JSON, and outputs
a formatted markdown report to stdout (or to the specified file).
"""

import argparse
import json
import os
import sys
from collections import defaultdict

def parse_json(text):
    """Extract JSON array from text that may contain LLM reasoning/thinking.

    Handles:
    - Pure JSON
    - Markdown code blocks (```json ... ```)
    - LLM reasoning before JSON (e.g. with --keep-thinking)
    - JSON array anywhere in the text
    """
    text = text.strip()

    # Try stripping markdown code blocks first
    cleaned = text
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Try parsing directly
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Search for JSON array within the text (handles LLM reasoning prefix)
    start = cleaned.find("[")
    if start == -1:
        raise json.JSONDecodeError("No JSON array found in text", cleaned, 0)

    # Find matching closing bracket with string awareness
    depth = 0
    end = start
    in_string = False
    escape_next = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end == start:
        raise json.JSONDecodeError("Could not find matching ] for [", cleaned, start)

    json_text = cleaned[start:end]
    return json.loads(json_text)


def _extract_company_from_text(text, company_names):
    """Find which company name from the list appears in the text."""
    if not text:
        return None
    text_lower = text.lower()
    for name in company_names:
        # Clean company name for matching
        clean = name.lower()
        # Handle common variations
        for variant in [clean, clean.replace(" ", ""), clean.replace("(", ""), clean.replace(")", "")]:
            if variant in text_lower and len(variant) > 2:
                return name
    return None


def parse_fallback(text):
    """Parse analysis from free-form text (LLM reasoning-only output).

    Used when the LLM output only reasoning text without JSON.
    Extracts ticker/company/sentiment/summary/quote from structured reasoning.

    The LLM reasoning format has TWO parts:
    1. A series of field blocks (Sentiment, Tags, Summary, Quote) for each stock
    2. A numbered list at the end mapping tickers to companies

    Strategy: For each ticker in the numbered list, find the Sentiment line
    that appears closest BEFORE the ticker in the text. This works because
    the field blocks precede the numbered list and each Sentiment line
    introduces a new block about one stock.
    """
    import re
    lines = text.split("\n")

    # Part 1: Find all Sentiment line positions and their block content
    sentiment_positions = []  # (line_index, block_content)
    current_block_lines = []
    current_sentiment = "NEUTRAL"

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()

        sent_match = re.match(r'[-\s]*Sentiment:\s*(.+)', line, re.IGNORECASE)
        if sent_match:
            # Save previous block
            if current_block_lines:
                sentiment_positions.append((i, "\n".join(current_block_lines), current_sentiment))
            current_block_lines = [line]
            raw_sent = sent_match.group(1).strip()
            for s in ["BULLISH", "BEARISH", "NEUTRAL"]:
                if s in raw_sent.upper():
                    current_sentiment = s
                    break
            continue

        current_block_lines.append(line)

    # Save last block
    if current_block_lines:
        sentiment_positions.append((len(lines) - 1, "\n".join(current_block_lines), current_sentiment))

    # Part 2: Find all ticker positions in the numbered list
    ticker_positions = []  # (line_index, ticker, company)
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        ticker_match = re.match(r'^[-\s]*\d+\.\s+\*?\*?(\S+?)\*?\*?\s*/\s*(.+)$', line)
        if ticker_match:
            ticker_positions.append((i, ticker_match.group(1), ticker_match.group(2).strip()))

    # Part 3: For each ticker in numbered list, find the nearest Sentiment line BEFORE it
    matched_blocks = set()
    entries = []

    for t_idx, (ticker_line_idx, ticker, company) in enumerate(ticker_positions):
        best_sentiment_idx = -1
        best_distance = float('inf')

        for s_idx, (sent_line_idx, block_text, sentiment) in enumerate(sentiment_positions):
            # Must be before the ticker line
            if sent_line_idx >= ticker_line_idx:
                continue
            # Must not have been used already
            if s_idx in matched_blocks:
                continue
            # Prefer the closest Sentiment line before this ticker
            distance = ticker_line_idx - sent_line_idx
            if distance < best_distance:
                best_distance = distance
                best_sentiment_idx = s_idx

        if best_sentiment_idx >= 0:
            matched_blocks.add(best_sentiment_idx)
            block_text = sentiment_positions[best_sentiment_idx][1]

            # Extract summary and quote from the block text
            summary = ""
            quote = ""
            tags = []
            for bline in block_text.split("\n"):
                bline = bline.strip()
                sm = re.match(r'[-\s]*Summary:\s*(.+)', bline)
                if sm:
                    summary = sm.group(1).strip()
                qm = re.match(r'[-\s]*(?:"|>)(.+)(?:"|>)?$', bline)
                if qm:
                    quote = qm.group(1).strip()
                tm = re.match(r'[-\s]*Tags:\s*(.+)', bline)
                if tm:
                    tags = [t.strip() for t in tm.group(1).split(',') if t.strip()]

            entries.append({
                "ticker": ticker,
                "company": company,
                "sentiment": sentiment_positions[best_sentiment_idx][2],
                "tags": tags,
                "summary": summary,
                "quote": quote,
            })

    return entries if entries else []


def format_report(entries, date_str):
    """Format parsed entries into markdown report."""
    # Group by sentiment
    groups = defaultdict(list)
    for entry in entries:
        sentiment = entry.get("sentiment", "NEUTRAL").upper()
        # Normalize
        if sentiment in ("BULLISH", "BEARISH", "NEUTRAL"):
            groups[sentiment].append(entry)
        else:
            groups["NEUTRAL"].append(entry)

    # Sort each group: BULLISH by most mentions/context, BEARISH similarly, NEUTRAL alphabetically
    for sentiment in groups:
        groups[sentiment].sort(key=lambda x: x.get("company", ""), reverse=(sentiment == "BULLISH"))

    # Build report
    lines = [f"CNBC Morning Audio — {date_str}", "=" * 40, ""]

    order = ["BULLISH", "BEARISH", "NEUTRAL"]
    labels = {
        "BULLISH": "BULLISH",
        "BEARISH": "BEARISH",
        "NEUTRAL": "NEUTRAL / ANALYST FOCUS",
    }

    for sentiment in order:
        if sentiment not in groups:
            continue
        entries_list = groups[sentiment]
        if not entries_list:
            continue

        lines.append(f"**{labels[sentiment]}**")
        lines.append("")

        for entry in entries_list:
            ticker = entry.get("ticker", "")
            company = entry.get("company", "Unknown")
            tags = entry.get("tags", [])
            summary = entry.get("summary", "")
            quote = entry.get("quote", "")

            # Format ticker
            ticker_display = f"${ticker}" if ticker else company

            # Format tags
            tag_str = ", ".join(tags) if tags else ""

            # Build line
            line = f"- **{ticker_display}** ({company})"
            if tag_str:
                line += f" — {tag_str}"
            if summary:
                line += f"\n  {summary}"
            lines.append(line)

        lines.append("")

    # Key themes: count most-mentioned tickers and generate a brief narrative
    ticker_counts = defaultdict(int)
    for entry in entries:
        t = entry.get("ticker") or entry.get("company", "")
        ticker_counts[t] += 1

    top_tickers = sorted(ticker_counts.items(), key=lambda x: -x[1])[:5]
    bullish_count = len(groups.get("BULLISH", []))
    bearish_count = len(groups.get("BEARISH", []))

    # Simple heuristic for themes
    themes = []
    if bullish_count > bearish_count * 2:
        themes.append("Bullish sentiment dominates the broadcast")
    elif bearish_count > bullish_count * 2:
        themes.append("Bearish sentiment dominates the broadcast")
    else:
        themes.append("Mixed sentiment across the broadcast")

    if top_tickers:
        top_names = [f"${t[0]}" if t[0] else t[0] for t in top_tickers[:3]]
        themes.append(f"Top mentions: {', '.join(top_names)}")

    lines.append("---")
    lines.append("")
    lines.append("**Key Themes:** " + ". ".join(themes) + ".")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Format CNBC analysis into report")
    parser.add_argument("date", help="Date string (YYYY-MM-DD)")
    parser.add_argument("--output", help="Output file path (default: stdout)", default=None)
    args = parser.parse_args()

    skill_dir = os.path.dirname(os.path.abspath(__file__))
    analysis_path = os.path.join(skill_dir, "analysis", f"{args.date}-analysis.md")
    output_path = args.output

    if not os.path.exists(analysis_path):
        print(f"ERROR: Analysis file not found: {analysis_path}", file=sys.stderr)
        sys.exit(1)

    with open(analysis_path, "r", encoding="utf-8") as f:
        text = f.read()

    try:
        entries = parse_json(text)
    except json.JSONDecodeError:
        # LLM output reasoning text without JSON — try fallback parser
        print("WARNING: No JSON found, parsing as free-form text", file=sys.stderr)
        entries = parse_fallback(text)
        if not entries:
            print("ERROR: Could not parse any entries from analysis file", file=sys.stderr)
            sys.exit(1)
    report = format_report(entries, args.date)

    if output_path:
        # Determine output directory
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Report saved to: {output_path}")
    else:
        print(report)

    print(f"\n# Parsed {len(entries)} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
