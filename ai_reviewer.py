import requests
import json

print("==================================================")
print("🤖 AI BACKTEST VALIDATOR (Timeout Fixed)")
print("==================================================")
api_key = input("Apni Google Gemini API Key paste karein: ").strip()

if not api_key:
    print("API key khali hai.")
    exit()

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
headers = {'Content-Type': 'application/json'}

file_path = "C:/avax_quant_system/backtests/backtest_lifetime_mega.py"
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        code = f.read()
except Exception as e:
    print(f"File nahi mili: {e}")
    exit()

print("\nAI aapka code check kar raha hai (Please wait up to 2 minutes)...")

prompt = "You are a Senior Quantitative Developer. Review this backtesting code for Lookahead Bias, Data Leakage, Logic Errors, and Slippage. Give a detailed report in Roman English.\n\nCode:\n"
prompt += code

payload = {"contents": [{"parts": [{"text": prompt}]}]}

try:
    # Timeout barha kar 120 seconds kar diya hai
    response = requests.post(url, headers=headers, json=payload, timeout=120)
    response_data = response.json()
    
    if 'candidates' in response_data:
        ai_reply = response_data['candidates'][0]['content']['parts'][0]['text']
        print("\n" + "="*60)
        print("🤖 AI BACKTEST REVIEW REPORT")
        print("="*60)
        print(ai_reply)
        print("="*60)
    else:
        print("\nError in API Response:")
        print(json.dumps(response_data, indent=2))
        
except Exception as e:
    print(f"\nConnection Error: {e}")
