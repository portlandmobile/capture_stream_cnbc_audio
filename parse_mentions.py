#!/usr/bin/env python3
"""Parse CNBC transcript for stock/company mentions with sentiment context."""

import re
from pathlib import Path

TRANSCRIPT_PATH = Path("recordings/2026-04-22.txt")
OUTPUT_PATH = Path("recordings/2026-04-22_mentions.txt")

# Known tickers and their company names
TICKERS = {
    "AMD": "AMD (Advanced Micro Devices)",
    "GE": "GE (General Electric)",
    "RTX": "RTX Corporation",
    "INTC": "Intel",
    "T": "AT&T",
    "TMUS": "T-Mobile",
    "VZ": "Verizon",
    "AAPL": "Apple",
    "GOOGL": "Alphabet/Google",
    "UNH": "UnitedHealth Group",
    "AVTR": "Avantor",
    "BABA": "Alibaba",
    "TSLA": "Tesla",
    "BA": "Boeing",
}

# Company names that map to tickers
COMPANY_NAMES = {
    "advanced micro": "AMD",
    "amd": "AMD",
    "ge": "GE",
    "general electric": "GE",
    "rtx": "RTX",
    "intel": "INTC",
    "at&t": "T",
    "att": "T",
    "t-mobile": "TMUS",
    "tmobile": "TMUS",
    "verizon": "VZ",
    "apple": "AAPL",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "google cloud": "GOOGL",
    "unitedhealth": "UNH",
    "unh": "UNH",
    "avantor": "AVTR",
    "avor": "AVTR",
    "boeing": "BA",
    "ba": "BA",
    "tesla": "TSLA",
    "nvidia": "NVDA",
    "spaceX": "SPAC",
    "cursor": "CURSOR",
    "anthropic": "ANTHROPIC",
    "xai": "XAI",
    "starlink": "STARLINK",
    "x": "X (Twitter)",
    "spac": "SPAC",
    "deutsche telecom": "DT",
    "paypal": "PYPL",
    "best buy": "BBY",
    "amazon": "AMZN",
    "adobe": "ADBE",
    "capital one": "COF",
    "discover": "DFS",
    "jetblue": "JBLU",
    "jet": "JBLU",
    "replicune": "RPLCN",
    "quantenium": "QTNM",
    "srs": "SRS",
    "pentwater": "Pentwater Fund",
    "seagate": "STX",
}

# Sentiment indicators (positive then negative — order matters for conflict)
POSITIVE = [
    "up ", "gain", "gain ", "higher", "rise", "rally", "bull",
    "strong", "beat", "beats", "beaten", "exceeded", "outperform",
    "outperforms", "great", "good", "positive", "exciting",
    "impressed", "proud", "favorable", "above estimates",
    "better than expected", "record", "crushing", "crush",
    "fan", "huge fan", "love that", "appreciate", "fabulous",
    "terrific", "commend", "doing well", "going up", "skyrocket",
    "soar", "surge", "momentum", "tailwind", "opportunity",
    "opportunities", "strong start", "on track", "stable",
    "impressive", "exciting", "pulsing", "duopoly", "solid",
    "better", "recovering", "turnaround", "growth", "ahead",
    "ahead of", "leading the way", "mad dash",
    "good business", "great business",
    "free cash flow story", "positive cash flow",
    "hit every target", "at the high end",
    "making people stickier", "increasing the value proposition",
    "embracing AI", "embrace AI",
    "up sharply", "up in the pre-market", "leading the way",
    "making progress", "making great progress",
    "all systems go", "good corridor", "record backlogs",
    "good start", "flawless", "commend", "applaud",
    "worth watching", "relevant",
    "better ARPU", "accelerating",
    "doing the best", "point people out",
    "very positive", "positive game",
    "good results", "better than expected",
    "stronger than", "outpacing",
    "top pick", "favorite",
    "up 11%", "up sharply", "up 91%", "up 12%", "up 92%",
    "91% for the year", "92%",
    "moving higher", "rocket ship", "on its own little rocket ship",
    "sold out", "huge demand",
    "very good",
]

NEGATIVE = [
    "down", "drop", "crush", "crushed", "crushing", "crash",
    "bad", "poor", "weak", "weaker", "disappointing", "disappointment",
    "miss", "missing", "under pressure", "headwind", "drag",
    "concern", "concerning", "cloud", "worried", "worry",
    "risk", "risks", "challenge", "challenging", "challenges",
    "problem", "problems", "issue", "issues", "trouble",
    "struggle", "struggling", "loss", "losses",
    "canceled", "cancel", "defer", "deferring", "deferred",
    "lower expectations", "get rid of",
    "impacting negatively", "negatively impacted",
    "overvalued", "bubble", "bust", "busted",
    "manipulation", "scratching their head", "many hurdles",
    "not creative", "hurdles",
    "down 5%", "down 2.7%", "down 6%", "down 10%", "down 12%",
    "stops down", "stock is not", "weakness",
    "small negative", "revenue miss", "miss",
    "limbo", "bad look",
    "cancellations", "canceled",
    "losses", "taking losses",
    "exposing", "exposed",
    "too far too fast",
    "faked out",
    "headwinds", "headwind",
    "significant cloud",
    "adverse effects",
]


def find_sentiment(sentence: str) -> tuple[str, float]:
    """Return (label, score) for a sentence. Score: +1 to +3 or -1 to -3."""
    s = sentence.lower()
    score = 0.0
    found_positive = []
    found_negative = []

    for w in POSITIVE:
        if w in s:
            score += 1.0
            found_positive.append(w.strip())
    
    for w in NEGATIVE:
        if w in s:
            score -= 1.0
            found_negative.append(w.strip())

    if score > 0:
        return ("Bullish", score, found_positive, found_negative)
    elif score < 0:
        return ("Bearish", score, found_positive, found_negative)
    else:
        return ("Neutral", 0.0, found_positive, found_negative)


def extract_mentions(transcript: str) -> list[dict]:
    """Extract all stock/company mentions with their surrounding context and sentiment."""
    sentences = re.split(r'(?<=[.!?])\s+', transcript.replace('\n', ' '))
    
    results = []
    seen = set()

    for sent in sentences:
        if len(sent) < 15:
            continue
            
        # Find all known tickers or company names in this sentence
        mentions = []
        s_lower = sent.lower()
        
        for company, ticker in COMPANY_NAMES.items():
            if company in s_lower:
                mentions.append((company, ticker))
        
        if not mentions:
            continue
        
        # Get sentiment
        label, score, pos_words, neg_words = find_sentiment(sent)
        
        # Get context window (surrounding sentences)
        idx = sentences.index(sent) if sent in sentences else -1
        context_start = max(0, idx - 2)
        context_end = min(len(sentences), idx + 3)
        context = " ".join(sentences[context_start:context_end]) if idx >= 0 else sent
        
        for company, ticker in mentions:
            key = f"{ticker}|{company}"
            if key not in seen:
                seen.add(key)
                results.append({
                    "ticker": ticker,
                    "company": company.title() if len(company) > 3 else company,
                    "sentiment": label,
                    "score": score,
                    "positive_words": pos_words,
                    "negative_words": neg_words,
                    "quote": sent.strip(),
                    "context": context.strip(),
                })

    return results


def format_results(mentions: list[dict]) -> str:
    """Format mentions into a readable report."""
    lines = []
    lines.append("=" * 80)
    lines.append("  CNBC MORNINGSIDE WITH JIM CRAMER — Stock & Company Mentions Report")
    lines.append(f"  Source: recordings/2026-04-22.mp3 | Transcribed: 2026-04-22")
    lines.append(f"  Total unique mentions: {len(mentions)}")
    lines.append("=" * 80)
    lines.append("")
    
    # Group by sentiment
    bullish = [m for m in mentions if m["sentiment"] == "Bullish"]
    bearish = [m for m in mentions if m["sentiment"] == "Bearish"]
    neutral = [m for m in mentions if m["sentiment"] == "Neutral"]
    
    def section(title, items):
        if not items:
            return
        lines.append(f"\n{'─' * 60}")
        lines.append(f"  {title} ({len(items)})")
        lines.append(f"{'─' * 60}")
        for m in items:
            emoji = "🟢" if m["sentiment"] == "Bullish" else "🔴" if m["sentiment"] == "Bearish" else "⚪"
            lines.append(f"\n  {emoji} **{m['ticker']}** ({m['company']})")
            lines.append(f"     Sentiment: {m['sentiment']} | Score: {m['score']:+.1f}")
            if m["positive_words"]:
                lines.append(f"     Bullish cues: {', '.join(m['positive_words'])}")
            if m["negative_words"]:
                lines.append(f"     Bearish cues: {', '.join(m['negative_words'])}")
            lines.append(f"     '{m['quote'][:120]}{'...' if len(m['quote']) > 120 else ''}'")
    
    section("🟢 BULLISH MENTIONS", bullish)
    section("🔴 BEARISH MENTIONS", bearish)
    section("⚪ NEUTRAL MENTIONS", neutral)
    
    lines.append("\n" + "=" * 80)
    
    return "\n".join(lines)


if __name__ == "__main__":
    text = TRANSCRIPT_PATH.read_text()
    mentions = extract_mentions(text)
    report = format_results(mentions)
    
    OUTPUT_PATH.write_text(report)
    print(report)
    print(f"\nSaved to: {OUTPUT_PATH}")
