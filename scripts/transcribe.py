# Minimal transcription script.
# Supports local Whisper if installed, else falls back to OpenAI Whisper API.
import argparse, json, os, sys
from pathlib import Path
from tqdm import tqdm

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, that's okay

def load_employee_names():
    """Load employee names from employees.json to use as Whisper hints."""
    try:
        # Try to find employees.json in the project root
        base_dir = Path(__file__).parent.parent
        employees_file = base_dir / "employees.json"
        
        if not employees_file.exists():
            print("employees.json not found, skipping name hints")
            return []
        
        with open(employees_file, 'r') as f:
            employees = json.load(f)
        
        names = [emp.get("name") for emp in employees if emp.get("name")]
        print(f"Loaded {len(names)} employee names for transcription hints: {', '.join(names)}")
        return names
    except Exception as e:
        print(f"Warning: Could not load employee names: {e}")
        return []

def whisper_transcribe_local(audio_path, model_name="small", prompt_hints=None):
    """Transcribe using local Faster-Whisper model (Optimized for speed)."""
    print(f"Loading Faster-Whisper model: {model_name}...")
    try:
        from faster_whisper import WhisperModel
        import torch
    except ImportError:
        print("Faster-Whisper not installed. Falling back to standard Whisper...")
        # Fallback to standard OpenAI Whisper if faster-whisper is missing
        try:
            import whisper
            import torch
        except ImportError:
             print("Whisper not installed. Install with: pip install -U openai-whisper faster-whisper")
             raise
        
        model = whisper.load_model(model_name)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Transcribing with STANDARD whisper model: {model_name} on {device.upper()}")
        
        # Add initial_prompt with employee names to improve recognition
        transcribe_kwargs = {"language": "en"}
        if prompt_hints:
            transcribe_kwargs["initial_prompt"] = f"Meeting with: {', '.join(prompt_hints)}."
        
        result = model.transcribe(audio_path, **transcribe_kwargs)
        transcript = []
        for seg in result.get("segments", []):
            transcript.append({"start": seg["start"], "end": seg["end"], "text": seg["text"]})
        return transcript

    # Faster-Whisper Implementation
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"Transcribing with FASTER-Whisper on {device.upper()} ({compute_type})")
    
    try:
        model = WhisperModel(model_name, device=device, compute_type=compute_type)
        
        # Add initial_prompt with employee names to improve recognition
        transcribe_kwargs = {"beam_size": 5, "language": "en"}
        if prompt_hints:
            transcribe_kwargs["initial_prompt"] = f"Meeting with: {', '.join(prompt_hints)}."
        
        segments, info = model.transcribe(audio_path, **transcribe_kwargs)
        
        transcript = []
        # segments is a generator, so iterating processes the audio
        for segment in segments:
            transcript.append({
                "start": segment.start, 
                "end": segment.end, 
                "text": segment.text
            })
        return transcript
    except Exception as e:
        print(f"Faster-Whisper failed: {e}. Falling back to standard Whisper.")
        # Fallback copy-paste from above (simplified)
        import whisper
        model = whisper.load_model(model_name)
        
        transcribe_kwargs = {"language": "en"}
        if prompt_hints:
            transcribe_kwargs["initial_prompt"] = f"Meeting with: {', '.join(prompt_hints)}."
        
        result = model.transcribe(audio_path, **transcribe_kwargs)
        return [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in result.get("segments", [])]

def whisper_transcribe_openai(audio_path, prompt_hints=None):
    """Transcribe using OpenAI Whisper API."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set. Set it as an environment variable.")
    
    if not api_key.startswith("sk-"):
        raise RuntimeError(f"Invalid API key format. API key should start with 'sk-'. Got: {api_key[:10]}...")
    
    print("Transcribing with OpenAI Whisper API...")
    print(f"Audio file: {audio_path}, exists: {os.path.exists(audio_path)}")
    
    # Try new OpenAI client API first (v1.0+)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        # Read file content once
        with open(audio_path, "rb") as f:
            audio_file_content = f.read()
        
        try:
            # Try with verbose_json and segments
            from io import BytesIO
            audio_file = BytesIO(audio_file_content)
            audio_file.name = os.path.basename(audio_path)
            
            # Build API call parameters
            api_params = {
                "model": "whisper-1",
                "file": audio_file,
                "response_format": "verbose_json",
                "timestamp_granularities": ["segment"]
            }
            
            # Add prompt with employee names if available
            if prompt_hints:
                api_params["prompt"] = f"Meeting with: {', '.join(prompt_hints)}."
            
            transcript_obj = client.audio.transcriptions.create(**api_params)
        except Exception as e1:
            # Fallback to simple json if verbose_json not supported
            print(f"verbose_json failed, trying json: {e1}")
            try:
                from io import BytesIO
                audio_file = BytesIO(audio_file_content)
                audio_file.name = os.path.basename(audio_path)
                transcript_obj = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )
            except Exception as e2:
                raise RuntimeError(f"Both verbose_json and json formats failed: {e1}, {e2}")
        
        # Convert OpenAI format to our format
        transcript = []
        
        # Handle different response formats
        if isinstance(transcript_obj, dict):
            # Dictionary format (from json response)
            if 'segments' in transcript_obj and transcript_obj['segments']:
                for seg in transcript_obj['segments']:
                    transcript.append({
                        "start": seg.get("start", 0.0),
                        "end": seg.get("end", 0.0),
                        "text": seg.get("text", "")
                    })
            elif 'text' in transcript_obj:
                # Single text response without segments - split into reasonable chunks
                text = transcript_obj['text'].strip()
                if text:
                    # Estimate duration (roughly 150 words per minute, 4 chars per word)
                    estimated_duration = max(1.0, len(text) / (150 * 4 / 60))
                    transcript.append({
                        "start": 0.0,
                        "end": estimated_duration,
                        "text": text
                    })
                else:
                    raise RuntimeError("OpenAI returned empty text")
        elif hasattr(transcript_obj, 'segments') and transcript_obj.segments:
            # Object format with segments attribute
            for seg in transcript_obj.segments:
                if isinstance(seg, dict):
                    transcript.append({
                        "start": seg.get("start", 0.0),
                        "end": seg.get("end", 0.0),
                        "text": seg.get("text", "")
                    })
                else:
                    transcript.append({
                        "start": getattr(seg, 'start', 0.0),
                        "end": getattr(seg, 'end', 0.0),
                        "text": getattr(seg, 'text', "")
                    })
        elif hasattr(transcript_obj, 'text'):
            # Object format with text attribute - split into reasonable chunks
            text = str(transcript_obj.text).strip()
            if text:
                # Estimate duration (roughly 150 words per minute, 4 chars per word)
                estimated_duration = max(1.0, len(text) / (150 * 4 / 60))
                transcript.append({
                    "start": 0.0,
                    "end": estimated_duration,
                    "text": text
                })
            else:
                raise RuntimeError("OpenAI returned empty text")
        else:
            # Fallback: try to get text from string representation
            full_text = str(transcript_obj).strip()
            if full_text and full_text != "None":
                # Estimate duration
                estimated_duration = max(1.0, len(full_text) / (150 * 4 / 60))
                transcript.append({
                    "start": 0.0,
                    "end": estimated_duration,
                    "text": full_text
                })
            else:
                raise RuntimeError("No transcript data extracted from OpenAI response")
        
        if not transcript:
            raise RuntimeError("No transcript data extracted from OpenAI response")
        
        # Validate transcript before returning
        for seg in transcript:
            if not isinstance(seg, dict):
                raise RuntimeError(f"Invalid segment type: {type(seg)}")
            if "text" not in seg or not seg["text"]:
                raise RuntimeError("Segment missing text")
            if "start" not in seg:
                seg["start"] = 0.0
            if "end" not in seg:
                seg["end"] = seg.get("start", 0.0) + 1.0
        
        print(f"Successfully created transcript with {len(transcript)} segments")
        return transcript
        
    except ImportError:
        # Try old OpenAI API style
        try:
            import openai
            openai.api_key = api_key
            
            with open(audio_path, "rb") as audio_file:
                transcript_obj = openai.Audio.transcribe(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json"
                )
            
            # Old API returns dict directly
            if isinstance(transcript_obj, dict):
                transcript = []
                if 'segments' in transcript_obj:
                    for seg in transcript_obj['segments']:
                        transcript.append({
                            "start": seg.get("start", 0.0),
                            "end": seg.get("end", 0.0),
                            "text": seg.get("text", "")
                        })
                else:
                    transcript.append({
                        "start": 0.0,
                        "end": 0.0,
                        "text": transcript_obj.get("text", "")
                    })
                return transcript
            else:
                raise RuntimeError("Unexpected response format from OpenAI API")
                
        except Exception as e:
            raise RuntimeError(f"Failed to use OpenAI API (tried both new and old styles): {e}")

def whisper_transcribe(audio_path, model_name="small", employee_names=None):
    """
    Transcribe audio. Prioritizes OpenAI API (faster, cloud-based) if available,
    falls back to local Whisper if API key is not set or API fails.
    """
    # Try OpenAI API first (much faster, better accuracy, cloud-based)
    if os.environ.get("OPENAI_API_KEY"):
        try:
            print("Attempting transcription with OpenAI Whisper API (faster, cloud-based)...")
            return whisper_transcribe_openai(audio_path, prompt_hints=employee_names)
        except Exception as e:
            print(f"OpenAI API failed ({e}), falling back to local Whisper...", file=sys.stderr)
            # Fall through to local Whisper
    
    # Fallback to local Whisper (slower but works offline)
    return whisper_transcribe_local(audio_path, model_name, prompt_hints=employee_names)

def save_transcript(transcript, out="transcript.json"):
    with open(out, "w") as f:
        json.dump(transcript, f, indent=2)
    print("Saved transcript to", out)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", help="audio file path")
    parser.add_argument("--model", default="small", help="whisper model name")
    parser.add_argument("--allow-fallback", action="store_true", help="Allow fallback to dummy transcript if Whisper fails")
    args = parser.parse_args()
    
    # Load employee names for better name recognition
    employee_names = load_employee_names()
    
    try:
        transcript = whisper_transcribe(args.audio, args.model, employee_names=employee_names)
    except Exception as e:
        # Only fallback if explicitly allowed
        if args.allow_fallback:
            print("WARNING: Falling back to dummy transcript due to:", e, file=sys.stderr)
            transcript = [
                {"start": 0.0, "end": 5.0, "text":"We need to create onboarding mockups by next Monday."},
                {"start": 5.1, "end": 9.0, "text":"Sanya will take that."},
                {"start": 9.1, "end": 15.0, "text":"Also, backend should add analytics events."}
            ]
        else:
            print(f"ERROR: Transcription failed: {e}", file=sys.stderr)
            print("Options:", file=sys.stderr)
            print("  1. Install local Whisper: pip install -U openai-whisper", file=sys.stderr)
            print("  2. Use OpenAI API: Set OPENAI_API_KEY environment variable", file=sys.stderr)
            sys.exit(1)
    save_transcript(transcript, out="transcript.json")
