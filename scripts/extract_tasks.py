# Uses Google Gemini API (FREE), OpenAI, or Ollama (Local) to extract action items.
# Logic: Try Gemini -> Fallback to OpenAI -> Fallback to Ollama (Local)

import argparse, os, json, time, sys, requests

PROMPT_TEMPLATE = '''You are an expert AI meeting assistant.
Your goal is to extract **meaningful, actionable tasks** from the meeting transcript below.

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

Return ONLY a valid JSON array of objects.
Each object MUST have:
- "text": (string) A full, definitive sentence describing the task.
- "assignee": (string or null) Who is responsible?
- "role": (string or null) Their role (e.g. "Engineer", "Designer").
- "deadline": (string YYYY-MM-DD or null) Date if mentioned.
- "priority": (string) "High", "Medium", or "Low".
- "confidence": (float) 0.0 to 1.0.

Consistency Rules:
- If a specific person is mentioned (e.g. "Sanya", "Jagan"), put them in "assignee".
- If no assignee is clear, use null.
- Default priority is "Medium".

Meeting date: {meeting_date}

Now extract action items from the transcript segments:
{{segments}}
'''


def call_gemini(prompt, model="gemini-1.5-flash"):
    """
    Call Google Gemini API.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set.")
    
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
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    
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

def call_ollama_fallback(prompt, model="llama3"):
    """
    Fallback to Local Ollama (Free, Private).
    Requires Ollama installed and 'ollama run llama3' executed previously.
    """
    url = "http://localhost:11434/api/generate"
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json" # Force JSON mode on Ollama
        }
        resp = requests.post(url, json=payload, timeout=300)
        if resp.status_code == 200:
            return resp.json().get("response", "")
        else:
            raise RuntimeError(f"Ollama returned {resp.status_code}")
    except Exception as e:
        raise RuntimeError(f"Ollama API call failed: {str(e)}. Ensure Ollama is running.")


def trim_segments_for_prompt(segments, max_chars=500000):
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

    trimmed_segments = trim_segments_for_prompt(segments)
    prompt = PROMPT_TEMPLATE.format(
        meeting_date=args.meeting_date or "2025-12-01",
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
