import requests
import json
import argparse

def get_enriched_analysis(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        transcript = f.read()

    # Use the /v1/chat/completions endpoint for better instruction following
    url = "http://127.0.0.1:8080/v1/chat/completions"

    payload = {
        "model": "gpt-3.5-turbo", # This is a placeholder name for llama.cpp
        "messages": [
            {
                "role": "system",
                "content": "You are a senior hedge fund analyst. Don't just list stocks. Identify 'Bearish' and 'Bullish' signals with direct quotes from the transcript, and summarize the macroeconomic context behind their picks. Ignore commercials."
            },
            {
                "role": "user",
                "content": f"Analyze this daily transcript for actionable stock recommendations:\n\n{transcript}"
            }
        ],
        # ENRICHMENT PARAMETERS
        "temperature": 1,      # High enough for nuance, low enough for facts
        "min_p": 0.05,           # Best for 'rich' vocabulary
        "presence_penalty": 0.3, # Prevents repetitive output
        "frequency_penalty": 0.2,
        "max_tokens": 4096,      # Allows for a much longer, detailed report
        "reasoning_format": "auto",
        "return_progress": True,
        "stream": False
    }

    print("Requesting deep analysis...")
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        content = response.json()['choices'][0]['message']['content']
        print("\n--- ENRICHED REPORT ---\n")
        print(content)
    else:
        print(f"Error: {response.status_code}")

if __name__ == "__main__":
    # Same file path passing logic as before
    import sys
    if len(sys.argv) > 1:
        get_enriched_analysis(sys.argv[1])
    else:
        print("Usage: python script.py <file_path>")