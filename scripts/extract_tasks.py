# Uses Google Gemini API (FREE), OpenAI, or Ollama (Local) to extract action items.
# Logic: Try Gemini -> Fallback to OpenAI -> Fallback to Ollama (Local)

import argparse, os, json, time, sys, requests
from pathlib import Path

PROMPT_TEMPLATE = '''You are an expert AI meeting assistant.
Your goal is to extract **meaningful, actionable tasks** from the meeting transcript below.

KNOWN TEAM MEMBERS:
{employee_names}

CRITICAL INSTRUCTIONS:
1.  **Synthesize, Don't Quote**: Do NOT just copy lines from the transcript. You must **rewrite** each task into a clear, standalone, professional sentence.
    *   BAD: "can you restart the server"
    *   GOOD: "Devin needs to restart the production server to resolve the latency issue."
    *   BAD: "update your daily tracker"
    *   GOOD: "Shagun must update her daily tracker by end of day."
    *   BAD: "checkout reducto.ai"
    *   GOOD: "Smriti needs to evaluate reducto.ai and provide an update tomorrow."
2.  **Context is King**: Use surrounding context (who said what, what came before/after) to understand the full task.
3.  **Be Definitive**: The "text" field should be a complete instruction.
4.  **Ignore Noise**: Ignore separate "Okay", "Yeah", "I will", "can you help" lines. Only capture actual commitments.
5.  **Correct Names**: If you see misspelled names like "Sangal", "Jagan", "Normal", correct them to the proper names from the team list above (e.g., "Sankalp", "Jagen", "Nirmal").

Return ONLY a valid JSON array of objects.
Each object MUST have:
- "text": (string) A full, definitive sentence describing the task.
- "assignee": (string or null) Who is responsible? Use the CORRECT spelling from the team list.
- "role": (string or null) Their role (e.g. "Engineer", "Designer").
- "deadline": (string YYYY-MM-DD or null) Date if mentioned.
- "priority": (string) "High", "Medium", or "Low".
- "confidence": (float) 0.0 to 1.0.

Consistency Rules:
- If a specific person is mentioned (e.g. "Sanya", "Jagan"), put them in "assignee" with CORRECT spelling.
- If no assignee is clear, use null.
- Default priority is "Medium".

Meeting date: {meeting_date}

Now extract action items from the transcript segments:
{segments}
'''

def load_employee_names():
    """Load employee names from employees.json."""
    try:
        base_dir = Path(__file__).parent.parent
        employees_file = base_dir / "employees.json"
        
        if not employees_file.exists():
            return []
        
        with open(employees_file, 'r') as f:
            employees = json.load(f)
        
        names = [emp.get("name") for emp in employees if emp.get("name")]
        return names
    except Exception as e:
        print(f"Warning: Could not load employee names: {e}", file=sys.stderr)
        return []

def call_gemini(prompt, model="gemini-2.5-flash"):
    """
    Call Google Gemini API.
    """
    # Try both GOOGLE_API_KEY and GEMINI_API_KEY for compatibility
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY or GEMINI_API_KEY not set.")
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(
            prompt,
            generation_config={"temperature": 0.0, "max_output_tokens": 8192}
        )
        return response.text
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {str(e)}")


def call_openai_fallback(prompt, model="gpt-4o-mini"):
    """
    Fallback to OpenAI.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.startswith('sk-'):
        raise RuntimeError("Invalid OPENAI_API_KEY: Must start with 'sk-' from https://platform.openai.com/account/api-keys")
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role":"user","content":prompt}],
            temperature=0.0,
            max_tokens=4000
        )
        return resp.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"OpenAI API call failed: {str(e)}")

def call_ollama_fallback(prompt, model="llama3.2"):
    """
    Fallback to Local Ollama (Free, Private).
    Requires Ollama installed and 'ollama run llama3.2' executed previously.
    """
    # First check if Ollama is running and model exists
    try:
        tags_resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        if tags_resp.status_code != 200:
            raise RuntimeError("Ollama server not responding")
        
        models = tags_resp.json().get("models", [])
        model_names = [m.get("name", "") for m in models]
        if not any(model in mn for mn in model_names):
            raise RuntimeError(f"Model '{model}' not found. Available models: {model_names}. Run 'ollama pull {model}' first.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Cannot connect to Ollama: {e}. Ensure Ollama is running.")
    
    url = "http://localhost:11434/api/generate"
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",  # Force JSON mode on Ollama
            "options": {
                "temperature": 0.0,
                "num_predict": 4096  # Limit output tokens
            }
        }
        print(f"Sending request to Ollama (this may take 1-2 minutes for large transcripts)...", file=sys.stdout)
        resp = requests.post(url, json=payload, timeout=120)  # Reduced from 300s to 120s
        if resp.status_code == 200:
            return resp.json().get("response", "")
        else:
            raise RuntimeError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama request timed out after 120 seconds. Try reducing transcript size or use a faster model.")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama API call failed: {str(e)}")


def trim_segments_for_prompt(segments, max_chars=100000):
    """
    Trim segments to fit within token limits.
    Reduced from 500K to 100K chars (~25K tokens) for better Ollama compatibility.
    """
    total = 0
    trimmed = []
    # Simple pass-through up to limit
    for s in segments:
        txt = s.get('text', '')
        est_len = len(txt) + 50
        if total + est_len > max_chars:
            break
        trimmed.append(s)
        total += est_len
    
    print(f"Trimmed transcript from {len(segments)} to {len(trimmed)} segments (~{total} chars)", file=sys.stdout)
    return trimmed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('transcript', help='transcript.json (merged or plain)')
    parser.add_argument('--meeting_date', default=None)
    args = parser.parse_args()
    
    # Handle file path
    transcript_path = args.transcript if os.path.isabs(args.transcript) else os.path.abspath(args.transcript)
    if not os.path.exists(transcript_path):
        print(f"ERROR: Transcript file not found: {transcript_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading transcript from: {transcript_path}", file=sys.stdout)
    with open(transcript_path) as f:
        segments = json.load(f)
    print(f"Loaded {len(segments)} transcript segments", file=sys.stdout)

    # Load employee names for better name recognition
    employee_names = load_employee_names()
    employee_names_str = ", ".join(employee_names) if employee_names else "No employee list provided"
    print(f"Using employee names: {employee_names_str}", file=sys.stdout)

    trimmed_segments = trim_segments_for_prompt(segments)
    prompt = PROMPT_TEMPLATE.format(
        meeting_date=args.meeting_date or "2025-12-01",
        employee_names=employee_names_str,
        segments=json.dumps(trimmed_segments, indent=2)
    )
    
    out = None
    # 1. Try Gemini
    try:
        print("Attempting extraction with Gemini...", file=sys.stdout)
        out = call_gemini(prompt)
        print("Gemini Success!", file=sys.stdout)
    except Exception as e:
        print(f"Gemini failed: {e}", file=sys.stderr)
        
        # 2. Try OpenAI
        try:
            print("Attempting extraction with OpenAI...", file=sys.stdout)
            out = call_openai_fallback(prompt)
            print("OpenAI Success!", file=sys.stdout)
        except Exception as e2:
            print(f"OpenAI failed: {e2}", file=sys.stderr)
            
            # 3. Try Ollama (Local)
            try:
                print("Attempting extraction with Ollama (Local Llama 3)...", file=sys.stdout)
                out = call_ollama_fallback(prompt)
                print("Ollama Success!", file=sys.stdout)
            except Exception as e3:
                print(f"Ollama failed: {e3}", file=sys.stderr)
                print("ALL LLM methods failed.", file=sys.stderr)

    tasks = []
    if out:
        print(f"RAW LLM RESPONSE:\n{out[:1000]}...", file=sys.stdout)
        try:
            import re
            m = re.search(r'\[.*\]', out, re.S)
            arr_text = m.group(0) if m else out
            tasks = json.loads(arr_text)
            print(f"Successfully parsed {len(tasks)} tasks", file=sys.stdout)
        except Exception as e:
            print(f"JSON Parsing failed: {e}", file=sys.stderr)
    
    tasks_path = os.path.abspath('tasks.json')
    with open(tasks_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, indent=2)
    print(f"Wrote tasks.json to {tasks_path} with {len(tasks)} items", file=sys.stdout)
