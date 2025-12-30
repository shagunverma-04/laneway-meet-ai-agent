"""
Quick diagnostic script to check which LLM providers are configured.
Run this to see what API keys are available.
"""

import os

# Try to load .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✓ Loaded .env file")
except ImportError:
    print("⚠ python-dotenv not installed (this is okay)")
except Exception as e:
    print(f"⚠ Could not load .env: {e}")

print("\n" + "="*60)
print("API KEY STATUS CHECK")
print("="*60)

# Check Gemini
gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
if gemini_key:
    print(f"\n✓ GEMINI API KEY: Found ({len(gemini_key)} chars)")
    print(f"  Preview: {gemini_key[:10]}...{gemini_key[-4:]}")
else:
    print("\n✗ GEMINI API KEY: Not found")
    print("  Set GOOGLE_API_KEY in .env file")
    print("  Get free key: https://aistudio.google.com/app/apikey")

# Check OpenAI
openai_key = os.environ.get("OPENAI_API_KEY")
if openai_key:
    print(f"\n✓ OPENAI API KEY: Found ({len(openai_key)} chars)")
    print(f"  Preview: {openai_key[:10]}...{openai_key[-4:]}")
    if not openai_key.startswith("sk-"):
        print("  ⚠ WARNING: Key doesn't start with 'sk-' (may be invalid)")
else:
    print("\n✗ OPENAI API KEY: Not found")
    print("  Set OPENAI_API_KEY in .env file")
    print("  Get key: https://platform.openai.com/account/api-keys")

# Check Ollama
print("\n" + "-"*60)
print("OLLAMA STATUS (Local AI)")
print("-"*60)
try:
    import requests
    resp = requests.get("http://localhost:11434/api/tags", timeout=2)
    if resp.status_code == 200:
        models = resp.json().get("models", [])
        print(f"\n✓ OLLAMA: Running ({len(models)} models available)")
        for model in models:
            print(f"  - {model.get('name', 'unknown')}")
    else:
        print(f"\n✗ OLLAMA: Server responded with status {resp.status_code}")
except requests.exceptions.ConnectionError:
    print("\n✗ OLLAMA: Not running")
    print("  Download: https://ollama.ai")
    print("  Then run: ollama pull llama3.2")
except Exception as e:
    print(f"\n✗ OLLAMA: Error - {e}")

print("\n" + "="*60)
print("RECOMMENDATION")
print("="*60)

if gemini_key:
    print("\n✓ You're all set! Gemini API is configured.")
    print("  Task extraction should work.")
elif openai_key:
    print("\n✓ You're all set! OpenAI API is configured.")
    print("  Task extraction should work.")
else:
    print("\n⚠ NO API KEYS CONFIGURED")
    print("\nQuickest solution:")
    print("  1. Go to: https://aistudio.google.com/app/apikey")
    print("  2. Create a free API key")
    print("  3. Add to .env file: GOOGLE_API_KEY=your-key-here")
    print("  4. Restart your application")

print("="*60 + "\n")
