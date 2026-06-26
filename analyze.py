#!/usr/bin/env python3
"""Per-sentence sentiment analysis of CNBC transcript."""
import re
from pathlib import Path
from collections import defaultdict

text = Path('recordings/2026-04-22.txt').read_text()
sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 15]

tickers = {
    'AMD': 'AMD (Advanced Micro Devices)',
    'GE': 'GE (General Electric)',
    'RTX': 'RTX Corporation',
    'INTC': 'Intel',
    'T': 'AT&T',
    'TMUS': 'T-Mobile',
    'VZ': 'Verizon',
    'AAPL': 'Apple',
    'GOOGL': 'Alphabet/Google',
    'UNH': 'UnitedHealth',
    'AVTR': 'Avantor',
    'BA': 'Boeing',
    'TSLA': 'Tesla',
    'NVDA': 'NVIDIA',
    'SPAC': 'SpaceX',
    'CURSOR': 'Cursor',
    'ANTHROPIC': 'Anthropic',
    'XAI': 'XAI',
    'ADBE': 'Adobe',
    'COF': 'Capital One',
    'DFS': 'Discover',
    'AMZN': 'Amazon',
    'PYPL': 'PayPal',
    'BBY': 'Best Buy',
    'STX': 'Seagate',
    'JBLU': 'JetBlue',
    'RPLCN': 'Recursion Pharma',
    'QTNM': 'Quantenium',
    'DT': 'Deutsche Telecom',
    'X': 'X (Twitter)',
}

# Map company names to tickers
company_to_ticker = {}
for t, name in tickers.items():
    company_to_ticker[name.lower()] = t
    company_to_ticker[name.lower().split('(')[0].strip()] = t
company_to_ticker['general electric'] = 'GE'
company_to_ticker['rtx corp'] = 'RTX'
company_to_ticker['advanced micro devices'] = 'AMD'
company_to_ticker['xai'] = 'XAI'
company_to_ticker['cursor'] = 'CURSOR'
company_to_ticker['capital one'] = 'COF'
company_to_ticker['discover'] = 'DFS'
company_to_ticker['best buy'] = 'BBY'

# Strong sentiment words with weights
POSITIVE = {
    'up': 1, 'gain': 1, 'higher': 1, 'rise': 1, 'rally': 1, 'strong': 2,
    'beat': 2, 'beats': 1, 'exceeded': 1, 'great': 2, 'good': 1,
    'positive': 2, 'exciting': 2, 'impressed': 2, 'proud': 1, 'favorable': 1,
    'above': 1, 'better': 1, 'better than expected': 2, 'record': 1,
    'crushing': 2, 'fan': 1, 'huge fan': 2, 'love': 2, 'appreciate': 1,
    'fabulous': 2, 'terrific': 2, 'commend': 2, 'doing well': 1,
    'momentum': 1, 'tailwind': 1, 'opportunity': 1, 'opportunities': 1,
    'on track': 2, 'stable': 1, 'impressive': 2, 'solid': 1,
    'recovering': 1, 'turnaround': 1, 'growth': 1, 'leading': 1,
    'progress': 1, 'systems go': 2, 'flawless': 2, 'applaud': 2,
    'worth watching': 1, 'relevant': 1, 'top pick': 2, 'favorite': 1,
    'hit every target': 2, 'high end': 1, 'stickier': 1,
    'value proposition': 1, 'embracing': 1, 'sharp': 1, 'sharply': 1,
    'pre-market': 1, 'recommending': 1, 'recommend': 1,
    'moving': 1, 'moving the stock': 1, 'recommendations': 1,
    'doing the best': 2, 'point people out': 1, 'very positive': 2,
    'free cash flow': 1, 'positive cash flow': 2, 'hit the number': 1,
    'ahead': 1, 'top': 1, 'sold out': 1, 'huge demand': 1, 'very good': 1,
    'up 11': 2, 'up 91': 3, 'up 12': 1, 'up 92': 3, 'rocket ship': 3,
    'crushing it': 2, 'better prepared': 2, 'stability': 1,
    'healthy': 1, 'bullish': 1, 'optimistic': 1, 'gaining': 1,
    'improving': 1, 'expanding': 1, 'thriving': 2, 'surge': 1,
    'outperform': 1, 'outperforms': 1, 'outperforming': 1,
    'beat estimates': 2, 'beat estimates': 2, 'above estimates': 2,
    'excitement': 1, 'excited': 1, 'exciting': 1,
    'confidence': 1, 'confident': 1, 'bull': 2,
}

NEGATIVE = {
    'down': 1, 'drop': 1, 'crash': 2, 'bad': 2, 'poor': 2, 'weak': 2,
    'weaker': 1, 'disappointing': 2, 'disappointment': 2, 'miss': 2,
    'under pressure': 1, 'headwind': 2, 'drag': 2, 'concern': 1,
    'concerning': 2, 'cloud': 1, 'worried': 1, 'risk': 1,
    'challenging': 1, 'challenges': 1, 'problem': 1, 'trouble': 1,
    'struggle': 1, 'loss': 1, 'losses': 1, 'canceled': 1, 'cancel': 1,
    'defer': 1, 'lower expectations': 1, 'overvalued': 2, 'bubble': 2,
    'bust': 2, 'manipulation': 2, 'scratching their head': 1,
    'hurdles': 1, 'limbo': 1, 'bad look': 2, 'cancellations': 1,
    'too far too fast': 1, 'faked out': 2, 'headwinds': 2,
    'significant cloud': 2, 'adverse effects': 2,
    'down 5': 1, 'down 2.7': 1, 'down 6': 1, 'down 10': 2,
    'down 12': 2, 'stops down': 2, 'weakness': 2, 'miss': 2,
    'decline': 1, 'declining': 1, 'slowing': 1, 'struggling': 2,
    'troubled': 2, 'underperform': 1, 'below': 1,
}

results = []

for i, sent in enumerate(sentences):
    s = sent.lower()
    found_tickers = []
    
    for t in tickers:
        if t.lower() in s:
            found_tickers.append(t)
    
    for company, t in company_to_ticker.items():
        if company in s and t not in found_tickers:
            found_tickers.append(t)
    
    if not found_tickers:
        continue
    
    score = 0
    pos_found = []
    neg_found = []
    
    # Check for phrase matches first
    phrase_map = {
        'better than expected': 2,
        'free cash flow': 1,
        'above estimates': 2,
        'systems go': 2,
        'too far too fast': -2,
        'bad look': -2,
        'significant cloud': -2,
        'under pressure': -1,
        'down 10': -2,
        'down 12': -2,
        'down 10 percent': -2,
        'down 5': -1,
        'down 2.7': -1,
        'down 6': -1,
        'stock is down': -1,
        'stock is down 10': -2,
        'stock is down 5': -1,
        'stock is down 2.7': -1,
        'stock is down 6': -1,
        'stock is down almost 3': -1,
    }
    
    for phrase, val in phrase_map.items():
        if phrase in s:
            score += val
            if val > 0:
                pos_found.append(phrase)
            else:
                neg_found.append(phrase)
    
    # Check for word matches (not in phrases)
    for w, v in POSITIVE.items():
        if w not in phrase_map and w in s:
            score += v
            pos_found.append(w)
    for w, v in NEGATIVE.items():
        if w not in phrase_map and w in s:
            score -= v
            neg_found.append(w)
    
    # Check for negative indicators
    neg_indicators = [
        "doesn't go", "don't need", "don't have", "don't think",
        "don't realize", "not going", "not necessarily",
    ]
    for ni in neg_indicators:
        if ni in s:
            score -= 1
            neg_found.append(ni)
    
    # Check for positive indicators
    pos_indicators = [
        "goes up", "went up", "is up", "going up", "will go up",
        "stock is up", "shares are up", "shares are higher",
        "stock is higher", "leading the way", "going to report",
    ]
    for pi in pos_indicators:
        if pi in s:
            score += 1
            pos_found.append(pi)
    
    if score > 0:
        label = 'Bullish'
    elif score < 0:
        label = 'Bearish'
    else:
        label = 'Neutral'
    
    for t in found_tickers:
        results.append({
            'ticker': t,
            'name': tickers[t],
            'sentiment': label,
            'score': score,
            'pos_words': list(set(pos_found)),
            'neg_words': list(set(neg_found)),
            'quote': sent[:200],
        })

# Group by ticker and aggregate
by_ticker = defaultdict(list)
for r in results:
    by_ticker[r['ticker']].append(r)

# Get the best sentiment per ticker
final = {}
for ticker, entries in by_ticker.items():
    # Use the most extreme sentiment
    max_score = max(entries, key=lambda x: abs(x['score']))
    final[ticker] = max_score

# Sort by absolute score
sorted_final = sorted(final.values(), key=lambda x: abs(x['score']), reverse=True)

# Print
print('='*80)
print('  CNBC MORNINGSIDE WITH JIM CRAMER')
print('  Stock & Company Mentions — Sentiment Analysis')
print('  Date: April 22, 2026 | 60-min live stream transcription')
print('='*80)
print(f'\nTotal mentions: {len(results)} | Unique tickers: {len(final)}')

bull = [r for r in sorted_final if r['sentiment']=='Bullish']
bear = [r for r in sorted_final if r['sentiment']=='Bearish']
neut = [r for r in sorted_final if r['sentiment']=='Neutral']

print(f'\n🟢 Bullish: {len(bull)}  |  🔴 Bearish: {len(bear)}  |  ⚪ Neutral: {len(neut)}')

def fmt(r):
    emoji = '🟢' if r['sentiment']=='Bullish' else '🔴' if r['sentiment']=='Bearish' else '⚪'
    lines = []
    lines.append(f'\n{emoji} {r["ticker"]}: {r["name"]}')
    lines.append(f'   Sentiment: {r["sentiment"]} | Score: {r["score"]:+d}')
    if r['pos_words']:
        lines.append(f'   Bullish signals: {", ".join(r["pos_words"][:8])}')
    if r['neg_words']:
        lines.append(f'   Bearish signals: {", ".join(r["neg_words"][:8])}')
    lines.append(f'   "{r["quote"]}"')
    return '\n'.join(lines)

print('\n--- BULLISH ---')
for r in bull:
    print(fmt(r))

print('\n--- BEARISH ---')
for r in bear:
    print(fmt(r))

print('\n--- NEUTRAL ---')
for r in neut:
    print(fmt(r))

print('\n' + '='*80)
print('  SUMMARY')
print('='*80)
print(f'\nMost bullish: {bull[0]["ticker"] if bull else "N/A"} ({bull[0]["score"]:+d})')
if bear:
    print(f'Most bearish: {bear[0]["ticker"]} ({bear[0]["score"]:+d})')
print(f'Most mentioned: {sorted(by_ticker.items(), key=lambda x: len(x[1]), reverse=True)[0][0]} ({len(sorted(by_ticker.items(), key=lambda x: len(x[1]), reverse=True)[0][1])} mentions)')
print()
