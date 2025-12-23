# Uses Google Gemini API (FREE) to extract action items from a transcript file.
# Requires GEMINI_API_KEY env var (free at https://aistudio.google.com/app/apikey)
# Falls back to OpenAI GPT-4o-mini if GEMINI_API_KEY not set.
import argparse, os, json, time, sys

PROMPT_TEMPLATE = '''You are an assistant that extracts and prioritizes **only meaningful, actionable tasks** from a meeting.

You are given transcript segments (each with start, end, and text).
Your job is to:
- Ignore chit-chat, comments, filler, and anything that is NOT a clear action someone should take.
- For each true action item, reconstruct a **full, natural sentence** even if the raw transcript is fragmented or partially captured.
- Use nearby context from the meeting (previous/next utterances) to complete the task sentence when needed.

Return ONLY a JSON array. Do NOT include any explanation, comments, or extra keys.
Each item in the array MUST have:
- "text": a single, clear, complete sentence describing the task (e.g. "We need to research how the founders started the business.")
- "assignee": name or email if mentioned, else null
- "role": suggested role (e.g. "Product Manager", "Backend Engineer", "Designer", "QA") or null
- "deadline": ISO date (YYYY-MM-DD) if mentioned or clearly implied, else null
- "priority": one of "High", "Medium", "Low"
- "confidence": float from 0.0 to 1.0

Relevance rules:
- Include tasks like: research, prepare, implement, fix, design, review, send, share, follow up, schedule, analyze, document, decide, plan.
- Exclude generic statements, status updates, or vague ideas without a clear action.
- If a task is only partially spoken in one segment, use the surrounding context to reconstruct the full intention as one clean sentence.

Prioritization rules:
- "High": urgent or blocking items, near-term deadlines, explicit commitments, or items the team agreed are critical.
- "Medium": clearly necessary work without strong urgency.
- "Low": nice-to-have ideas, long-term suggestions, or optional improvements.

Meeting date: {meeting_date}

Example:
Transcript segment: "Sanya, can you make the onboarding mockups by next Monday?"
Output:
[{{
  "text": "Sanya will create the onboarding mockups by next Monday.",
  "assignee": "Sanya",
  "role": "Product Designer",
  "deadline": "2025-12-08",
  "priority": "High",
  "confidence": 0.95
}}]

Now extract action items from the following transcript segments (JSON array of objects with at least {{start,end,text}}):
{{segments}}
'''


def call_gemini(prompt, model="gemini-1.5-flash"):
    """
    Call Google Gemini API (FREE) for task extraction.
    Free tier: 15 requests per minute, generous daily limits
    Models: gemini-1.5-flash (fast, free), gemini-1.5-pro (better quality, free)
    Get API key: https://aistudio.google.com/app/apikey
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Get FREE API key from https://aistudio.google.com/app/apikey")
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        
        # Use the specified model
        model_instance = genai.GenerativeModel(model)
        
        response = model_instance.generate_content(
            prompt,
            generation_config={
                "temperature": 0.0,  # Deterministic output
                "max_output_tokens": 4096,  # Large enough for multiple tasks
            }
        )
        
        return response.text
            
    except ImportError:
        raise RuntimeError("google-generativeai package not installed. Run: pip install google-generativeai")
    except Exception as e:
        raise RuntimeError(f"Gemini API call failed: {str(e)}")


def call_openai_fallback(prompt, model="gpt-4o-mini"):
    """
    Fallback to OpenAI GPT-4o-mini if Gemini is not available.
    Requires OPENAI_API_KEY env var.
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
            max_tokens=2000
        )
        return resp.choices[0].message.content
    except ImportError:
        raise RuntimeError("openai package not installed")
    except Exception as e:
        raise RuntimeError(f"OpenAI API call failed: {str(e)}")


def trim_segments_for_prompt(segments, max_chars=20000):
    """
    Reduce prompt size for latency/cost:
    - Prefer segments that are likely to contain actions (simple keyword heuristic).
    - Always enforce a hard character cap so the prompt stays bounded.
    """
    action_keywords = [
        'need', 'please', 'can you', 'could you', 'would you',
        'will ', 'we will', 'i will', 'we should', 'should ', 'must',
        'assign', "let's", 'todo', 'follow up', 'take care of', 'make sure',
        'remember to', 'ensure', 'schedule', 'plan', 'prepare', 'send', 'share'
    ]

    def looks_actiony(txt: str) -> bool:
        lower = txt.lower()
        return any(k in lower for k in action_keywords)

    prioritized = [s for s in segments if looks_actiony(s.get('text', ''))]
    if not prioritized:
        prioritized = list(segments)  # fallback: use everything

    # If the prioritized text is very long, downsample roughly evenly across the meeting
    est_total_chars = sum(len(s.get('text', '')) for s in prioritized)
    if est_total_chars > max_chars * 1.5 and len(prioritized) > 0:
        avg_len = max(1, est_total_chars // len(prioritized))
        approx_segments = max(1, max_chars // avg_len)
        step = max(1, len(prioritized) // approx_segments)
        prioritized = [s for idx, s in enumerate(prioritized) if idx % step == 0]

    trimmed = []
    total = 0
    for s in prioritized:
        txt = s.get('text', '')
        # conservative estimate: include JSON overhead
        est_len = len(txt) + 100
        if total + est_len > max_chars:
            break
        trimmed.append(s)
        total += est_len
    return trimmed


def build_heuristic_tasks(segments):
    """
    Very simple heuristic: sentences containing action-like keywords.
    Used as a fallback when the model returns no tasks or parsing fails.
    """
    keywords = [
        'need', 'please', 'can you', 'could you', 'would you',
        'will ', 'we will', 'i will', 'we should', 'should ', 'must',
        'assign', "let's", 'todo', 'follow up', 'take care of', 'action item',
        'next step', 'next steps', 'deadline', 'by tomorrow', 'by next week',
        'research', 'prepare', 'analyze', 'investigate', 'document', 'schedule',
        'plan', 'design', 'implement', 'fix', 'review', 'send', 'share'
    ]

    def context_text(idx: int) -> str:
        """Build a fuller sentence using previous and next segments as context."""
        pieces = []
        if idx - 1 >= 0:
            prev = (segments[idx - 1].get('text') or '').strip()
            if prev:
                pieces.append(prev)
        cur = (segments[idx].get('text') or '').strip()
        if cur:
            pieces.append(cur)
        if idx + 1 < len(segments):
            nxt = (segments[idx + 1].get('text') or '').strip()
            if nxt:
                pieces.append(nxt)
        # Join and collapse whitespace
        return ' '.join(pieces).strip()

    tasks = []
    for i, s in enumerate(segments):
        raw_txt = s.get('text', '')
        lower = raw_txt.lower()
        if any(k in lower for k in keywords):
            full_sentence = context_text(i)
            tasks.append({
                "text": full_sentence,
                "assignee": None,
                "role": None,
                "deadline": None,
                "priority": "Medium",
                "confidence": 0.6,
                "source_segment": s
            })
    return tasks

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('transcript', help='transcript.json (merged or plain)')
    parser.add_argument('--meeting_date', default=None)
    args = parser.parse_args()
    
    # Handle file path - check if it's relative or absolute
    transcript_path = args.transcript if os.path.isabs(args.transcript) else os.path.abspath(args.transcript)
    if not os.path.exists(transcript_path):
        print(f"ERROR: Transcript file not found: {transcript_path}", file=sys.stderr)
        print(f"Current working directory: {os.getcwd()}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading transcript from: {transcript_path}", file=sys.stdout)
    with open(transcript_path) as f:
        segments = json.load(f)
    print(f"Loaded {len(segments)} transcript segments", file=sys.stdout)

    # Optimize latency and token usage by trimming what we send to the model.
    trimmed_segments = trim_segments_for_prompt(segments)
    prompt = PROMPT_TEMPLATE.format(
        meeting_date=args.meeting_date or "2025-12-01",
        segments=json.dumps(trimmed_segments, indent=2)
    )
    try:
        # Try Gemini first (FREE), fallback to OpenAI if not available
        try:
            out = call_gemini(prompt)
            print(f"Gemini response received (length: {len(out)})", file=sys.stdout)
        except RuntimeError as gemini_error:
            if "GEMINI_API_KEY" in str(gemini_error):
                print("Gemini API key not set, trying OpenAI fallback...", file=sys.stderr)
                out = call_openai_fallback(prompt)
                print(f"OpenAI response received (length: {len(out)})", file=sys.stdout)
            else:
                raise
        # Try to parse JSON from the response:
        import re, ast
        m = re.search(r'\[.*\]', out, re.S)
        if m:
            arr_text = m.group(0)
        else:
            arr_text = out
        tasks = json.loads(arr_text)
        print(f"Successfully parsed {len(tasks)} tasks", file=sys.stdout)

        # If the model returned an empty list, fall back to heuristic extraction
        if not tasks:
            print("Model returned empty task list; falling back to heuristic extraction.", file=sys.stderr)
            tasks = build_heuristic_tasks(segments)
    except Exception as e:
        print(f"LLM API call failed or parsing failed: {e}", file=sys.stderr)
        print(f"Response was: {out[:500] if 'out' in locals() else 'N/A'}", file=sys.stderr)
        print("Falling back to heuristic extraction.", file=sys.stderr)
        tasks = build_heuristic_tasks(segments)
    
    # Always write tasks.json, even if empty
    tasks_path = os.path.abspath('tasks.json')
    with open(tasks_path, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, indent=2)
    print(f"Wrote tasks.json to {tasks_path} with {len(tasks)} items", file=sys.stdout)
    if len(tasks) == 0:
        print("Warning: No tasks extracted. Check GEMINI_API_KEY (or OPENAI_API_KEY) and transcript content.", file=sys.stderr)
        print(f"Transcript had {len(segments)} segments, trimmed to {len(trimmed_segments)} for prompt", file=sys.stderr)
