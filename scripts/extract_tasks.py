# Uses Google Gemini API (FREE), OpenAI, or Ollama (Local) to extract action items.
# Logic: Try Gemini -> Fallback to OpenAI -> Fallback to Ollama (Local)

import argparse, os, json, time, sys, requests
from pathlib import Path

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, that's okay


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
            generation_config={"temperature": 0.0, "max_output_tokens": 16384}
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
    errors = []
    
    # 1. Try Gemini
    try:
        print("Attempting extraction with Gemini...", file=sys.stdout)
        gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            raise RuntimeError("No Gemini API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable.")
        out = call_gemini(prompt)
        print("✓ Gemini Success!", file=sys.stdout)
    except Exception as e:
        error_msg = f"Gemini failed: {e}"
        print(error_msg, file=sys.stderr)
        errors.append(error_msg)
        
        # 2. Try OpenAI
        try:
            print("\nAttempting extraction with OpenAI...", file=sys.stdout)
            openai_key = os.environ.get("OPENAI_API_KEY")
            if not openai_key:
                raise RuntimeError("No OpenAI API key found. Set OPENAI_API_KEY environment variable.")
            out = call_openai_fallback(prompt)
            print("✓ OpenAI Success!", file=sys.stdout)
        except Exception as e2:
            error_msg = f"OpenAI failed: {e2}"
            print(error_msg, file=sys.stderr)
            errors.append(error_msg)
            
            # 3. Try Ollama (Local)
            try:
                print("\nAttempting extraction with Ollama (Local Llama 3)...", file=sys.stdout)
                out = call_ollama_fallback(prompt)
                print("✓ Ollama Success!", file=sys.stdout)
            except Exception as e3:
                error_msg = f"Ollama failed: {e3}"
                print(error_msg, file=sys.stderr)
                errors.append(error_msg)
                
                # All methods failed - print comprehensive error
                print("\n" + "="*60, file=sys.stderr)
                print("✗ ALL LLM METHODS FAILED", file=sys.stderr)
                print("="*60, file=sys.stderr)
                print("\nErrors encountered:", file=sys.stderr)
                for i, err in enumerate(errors, 1):
                    print(f"{i}. {err}", file=sys.stderr)
                
                print("\n" + "-"*60, file=sys.stderr)
                print("SOLUTIONS:", file=sys.stderr)
                print("-"*60, file=sys.stderr)
                
                # Check which keys are set
                has_gemini = bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
                has_openai = bool(os.environ.get("OPENAI_API_KEY"))
                
                print(f"\nAPI Keys Status:", file=sys.stderr)
                print(f"  Gemini: {'✓ SET' if has_gemini else '✗ NOT SET'}", file=sys.stderr)
                print(f"  OpenAI: {'✓ SET' if has_openai else '✗ NOT SET'}", file=sys.stderr)
                
                print(f"\nTo fix this issue, choose ONE of these options:", file=sys.stderr)
                print(f"  1. Set up Gemini (FREE): Get API key from https://aistudio.google.com/app/apikey", file=sys.stderr)
                print(f"     Then set: GOOGLE_API_KEY=your-key-here in .env file", file=sys.stderr)
                print(f"  2. Set up OpenAI: Get API key from https://platform.openai.com/account/api-keys", file=sys.stderr)
                print(f"     Then set: OPENAI_API_KEY=sk-... in .env file", file=sys.stderr)
                print(f"  3. Install Ollama (FREE, Local): Download from https://ollama.ai", file=sys.stderr)
                print(f"     Then run: ollama pull llama3.2", file=sys.stderr)
                print("="*60 + "\n", file=sys.stderr)

    tasks = []
    if out:
        print(f"RAW LLM RESPONSE (first 1000 chars):\n{out[:1000]}...", file=sys.stdout)
        print(f"\nRAW LLM RESPONSE (last 500 chars):\n...{out[-500:]}", file=sys.stdout)
        
        try:
            import re
            # Try to extract JSON from markdown code blocks first
            # Pattern 1: ```json ... ```
            json_match = re.search(r'```json\s*(.*?)\s*```', out, re.S | re.I)
            if json_match:
                arr_text = json_match.group(1).strip()
                print("Found JSON in markdown code block", file=sys.stdout)
            else:
                # Pattern 2: ``` ... ``` (without language specifier)
                code_match = re.search(r'```\s*(.*?)\s*```', out, re.S)
                if code_match:
                    arr_text = code_match.group(1).strip()
                    print("Found code in markdown block", file=sys.stdout)
                else:
                    # Pattern 3: Just find the JSON array
                    array_match = re.search(r'\[.*\]', out, re.S)
                    arr_text = array_match.group(0) if array_match else out
                    print("Extracted JSON array from response", file=sys.stdout)
            
            tasks = json.loads(arr_text)
            print(f"\n✓ Successfully parsed {len(tasks)} tasks", file=sys.stdout)
            
            # Print each task for verification
            for i, task in enumerate(tasks, 1):
                print(f"\nTask {i}:", file=sys.stdout)
                print(f"  Text: {task.get('text', 'N/A')}", file=sys.stdout)
                print(f"  Assignee: {task.get('assignee', 'N/A')}", file=sys.stdout)
                print(f"  Priority: {task.get('priority', 'N/A')}", file=sys.stdout)
                print(f"  Deadline: {task.get('deadline', 'N/A')}", file=sys.stdout)
                
        except json.JSONDecodeError as e:
            print(f"\n✗ JSON Parsing failed: {e}", file=sys.stderr)
            print(f"Attempting to repair incomplete JSON...", file=sys.stderr)
            
            # Try to repair incomplete JSON by adding missing closing brackets
            try:
                # Count opening and closing brackets
                open_braces = arr_text.count('{')
                close_braces = arr_text.count('}')
                open_brackets = arr_text.count('[')
                close_brackets = arr_text.count(']')
                
                # Add missing closing brackets
                repaired_text = arr_text
                if close_braces < open_braces:
                    repaired_text += '\n' + ('  }' * (open_braces - close_braces))
                if close_brackets < open_brackets:
                    repaired_text += '\n' + (']' * (open_brackets - close_brackets))
                
                # Try parsing the repaired JSON
                tasks = json.loads(repaired_text)
                print(f"✓ Successfully repaired and parsed {len(tasks)} tasks from incomplete response", file=sys.stdout)
                
                # Print each task for verification
                for i, task in enumerate(tasks, 1):
                    print(f"\nTask {i}:", file=sys.stdout)
                    print(f"  Text: {task.get('text', 'N/A')}", file=sys.stdout)
                    print(f"  Assignee: {task.get('assignee', 'N/A')}", file=sys.stdout)
                    print(f"  Priority: {task.get('priority', 'N/A')}", file=sys.stdout)
                    print(f"  Deadline: {task.get('deadline', 'N/A')}", file=sys.stdout)
                    
            except Exception as repair_error:
                print(f"✗ JSON repair failed: {repair_error}", file=sys.stderr)
                print(f"Failed to parse text (first 500 chars):\n{arr_text[:500] if 'arr_text' in locals() else 'N/A'}", file=sys.stderr)
                # Save the raw response for debugging
                debug_path = os.path.abspath('llm_response_debug.txt')
                with open(debug_path, 'w', encoding='utf-8') as df:
                    df.write(out)
                print(f"Saved raw LLM response to {debug_path} for debugging", file=sys.stderr)
        except Exception as e:
            print(f"\n✗ Unexpected error during parsing: {e}", file=sys.stderr)
    else:
        print("\n✗ No LLM response received - all methods failed", file=sys.stderr)
    
    tasks_path = os.path.abspath('tasks.json')
    with open(tasks_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)
    print(f"\n{'='*60}", file=sys.stdout)
    print(f"Wrote {len(tasks)} tasks to {tasks_path}", file=sys.stdout)
    print(f"{'='*60}", file=sys.stdout)
