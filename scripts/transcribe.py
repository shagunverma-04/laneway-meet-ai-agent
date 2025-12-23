# Minimal transcription script.
# Supports local Whisper if installed, else falls back to OpenAI Whisper API.
import argparse, json, os, sys
from tqdm import tqdm

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, that's okay

def whisper_transcribe_local(audio_path, model_name="small"):
    """Transcribe using local Whisper model."""
    try:
        import whisper
        import torch
    except Exception as e:
        print("Whisper not installed. Install with: pip install -U openai-whisper")
        raise
    model = whisper.load_model(model_name)
    
    # Check and report GPU availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Transcribing with local whisper model: {model_name} on {device.upper()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    
    result = model.transcribe(audio_path, language='en')
    # result contains 'segments' with start, end, text
    transcript = []
    for seg in result.get("segments", []):
        transcript.append({"start": seg["start"], "end": seg["end"], "text": seg["text"]})
    return transcript

def whisper_transcribe_openai(audio_path):
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
            transcript_obj = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
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

def whisper_transcribe(audio_path, model_name="small"):
    """
    Transcribe audio. Prioritizes OpenAI API (faster, cloud-based) if available,
    falls back to local Whisper if API key is not set or API fails.
    """
    # Try OpenAI API first (much faster, better accuracy, cloud-based)
    if os.environ.get("OPENAI_API_KEY"):
        try:
            print("Attempting transcription with OpenAI Whisper API (faster, cloud-based)...")
            return whisper_transcribe_openai(audio_path)
        except Exception as e:
            print(f"OpenAI API failed ({e}), falling back to local Whisper...", file=sys.stderr)
            # Fall through to local Whisper
    
    # Fallback to local Whisper (slower but works offline)
    return whisper_transcribe_local(audio_path, model_name)

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
    try:
        transcript = whisper_transcribe(args.audio, args.model)
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
