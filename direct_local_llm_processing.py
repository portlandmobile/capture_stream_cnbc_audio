import requests
import json
import argparse
import sys
import os

def main():
    # 1. Setup Argument Parsing
    parser = argparse.ArgumentParser(description="Extract stock data from a transcript using local Llama.cpp server.")
    parser.add_argument("file_path", help="Path to the transcript .txt file")
    parser.add_argument("--url", default="http://127.0.0.1:8080/completion", help="Llama.cpp server URL")
    args = parser.parse_args()

    # 2. Validate File
    if not os.path.exists(args.file_path):
        print(f"Error: File '{args.file_path}' not found.")
        sys.exit(1)

    with open(args.file_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    # 3. Construct the Prompt
    # We use a structured system prompt to force the model into "Extraction Mode"
    prompt = f"""### System:
Below is the transcript of a stock analysis podcast. 
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
  - `macro` — mentioned in context of broad market/economic discussion

The transcript contains advertisement. Do not output companies or info related to the ad mention.  Otherwise, capture the verbatim sentence(s) around each mention as a short quote for reference.

### Transcript:
{transcript}

### Response:
["""

    # 4. Prepare Payload for Llama.cpp Server
    payload = {
        "prompt": prompt,
        "temperature": 0.7,
        "max_token": 4096,
        "reasoning_format": "auto",
        "return_progress": True,
        "top_k": 40,
        "n_predict": 2048,      # Enough space for a long list of stocks
        "stream": False,
        "cache_prompt": True,   # High-efficiency flag: keeps the prompt in KV cache
        "slot_id": 0,           # Ensures it uses the same memory slot
        "stop": ["]", "###"]    # Helps the model know when the JSON list is done
    }
       # "temperature": 0.7,      # High enough for nuance, low enough for facts
       #  "min_p": 0.05,           # Best for 'rich' vocabulary
       #  "presence_penalty": 0.3, # Prevents repetitive output
       #  "frequency_penalty": 0.2,
       #  "max_tokens": 4096,      # Allows for a much longer, detailed report
       #  "stream": False

    print(f"Sending {len(transcript)} characters to LLM at {args.url}...")

    try:
        response = requests.post(args.url, json=payload, timeout=300)
        response.raise_for_status()
        
        # Llama.cpp returns content in the 'content' field
        raw_output = response.json().get("content", "")
        
        # Since we started the prompt with '[', we prepend it back if needed
        final_json = "[" + raw_output.strip()
        if not final_json.endswith("]"):
            final_json += "]"

        # 5. Save Output
        output_filename = f"report_{os.path.basename(args.file_path).replace('.txt', '.json')}"
        with open(output_filename, "w") as f:
            f.write(final_json)
            
        print(f"✅ Success! Report generated: {output_filename}")

    except Exception as e:
        print(f"❌ Failed to process: {e}")

if __name__ == "__main__":
    main()